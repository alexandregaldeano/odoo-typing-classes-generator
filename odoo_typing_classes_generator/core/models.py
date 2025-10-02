import dataclasses
import keyword
import logging
import re
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Union,
    get_args,
    get_origin,
)

from odoo.tools import ConstantMapping

_logger = logging.getLogger(__name__)


def _snake_case_to_pascal_case(snake_case_str: str) -> str:
    """
    Converts a snake_case string to PascalCase.
    """
    pascal_case_str = ""
    for word in snake_case_str.split("_"):
        if not word:
            continue
        pascal_case_str += word[0].upper()
        if len(word) > 1:
            pascal_case_str += word[1:]
    return pascal_case_str


@dataclasses.dataclass
class ImportData:
    package_name: str
    class_name: Optional[str] = None
    alias: Optional[str] = None

    def serialize(self) -> str:
        if self.class_name:
            import_str = f"from {self.package_name} import {self.class_name}"
        else:
            import_str = f"import {self.package_name}"
        if self.alias:
            import_str += f" as {self.alias}"
        return import_str

    def __hash__(self) -> int:
        return hash((self.package_name, self.class_name, self.alias))


@dataclasses.dataclass
class TypeData:
    value: type
    imports: Set[ImportData] = dataclasses.field(init=False)

    def __post_init__(self):
        self.imports = TypeData.collect_imports(self.value)

    @staticmethod
    def collect_imports(type_hint: type) -> Set[ImportData]:
        if type_hint.__module__ == "builtins":
            return set()
        if type_hint.__module__ != "typing":
            return {
                ImportData(
                    package_name=type_hint.__module__,
                    class_name=type_hint.__name__,
                ),
            }
        origin_type = get_origin(type_hint)
        if origin_type is None:
            imports = {
                ImportData(
                    package_name="typing",
                    class_name="Any",
                ),
            }
        elif origin_type.__module__ == "typing":
            imports = {
                ImportData(
                    package_name=origin_type.__module__,
                    class_name=origin_type._name,
                ),
            }
        elif origin_type.__module__ == "builtins":
            imports = {
                ImportData(
                    package_name="typing",
                    class_name=origin_type.__name__.capitalize(),
                ),
            }
        elif origin_type.__name__ in ["Callable", "Generator"]:
            imports = {
                ImportData(
                    package_name="typing",
                    class_name=origin_type.__name__,
                ),
            }
        else:
            imports = {
                ImportData(
                    package_name=origin_type.__module__,
                    class_name=origin_type.__name__,
                ),
            }
        for arg in get_args(type_hint):
            if not isinstance(arg, list):
                imports |= TypeData.collect_imports(arg)
                continue
            for item in arg:
                imports |= TypeData.collect_imports(item)
        return imports

    def serialize(self) -> str:
        if self.value == type(None):
            return "None"
        if self.value.__module__ != "typing":
            return self.value.__name__
        value_str = str(self.value)
        for import_data in self.imports:
            value_str = value_str.replace(f"{import_data.package_name}.", "")
        return value_str.replace("NoneType", "None")


@dataclasses.dataclass
class FunctionArgumentData:
    name: str
    type: Optional[TypeData] = None
    default: Any = None
    has_default: bool = False
    is_vararg: bool = False
    is_kwarg: bool = False

    def serialize(self) -> str:
        arg_str = ""
        if self.is_vararg:
            arg_str += "*"
        elif self.is_kwarg:
            arg_str += "**"
        arg_str += self.name
        if self.type:
            arg_str += f": {self.type.serialize()}"
        if self.has_default:
            if self.type:
                arg_str += " = "
            else:
                arg_str += "="
            if self.default is None or self.default == type(None):
                arg_str += "None"
            elif type(self.default) == type:
                arg_str += self.default.__name__
            elif isinstance(self.default, str):
                # Escape quotes in string defaults
                default = self.default.replace('"', '\\"')
                arg_str += f'"{default}"'
            elif isinstance(self.default, ConstantMapping):
                arg_str += f"ConstantMapping({self.default[0]})"
            else:
                arg_str += str(self.default)
        return arg_str


@dataclasses.dataclass
class FunctionData:
    name: str
    args: List[FunctionArgumentData]
    type: Union[TypeData, str, None] = None
    is_class_method: bool = False
    is_static_method: bool = False

    def serialize(self, escape_pattern: re.Pattern) -> str:
        function_str = ""
        if self.is_class_method:
            function_str += "    @classmethod\n"
        elif self.is_static_method:
            function_str += "    @staticmethod\n"
        function_str += f"    def {self.name}("
        function_str += ", ".join(arg.serialize() for arg in self.args)
        function_str += ")"
        if self.type:
            function_str += f" -> {self.type.serialize()}"
        function_str = re.sub(escape_pattern, r'"\1"', function_str)
        function_str += ":\n        ...\n"
        return function_str


@dataclasses.dataclass
class FieldData:
    name: str
    type: Union[TypeData, str]
    related: Optional[str]

    def serialize(
        self, merged_models_data_by_odoo_model_name: Dict[str, "MergedModelData"]
    ) -> str:
        if isinstance(self.type, str):
            serialized_type = merged_models_data_by_odoo_model_name[
                self.type
            ].unique_class_name
            # We cannot use Literal[False] here, because when iterating over the field,
            # the IDE wouldn't know which of the two types the elements have.
            serialized_type = f'Union["{serialized_type}", bool]'
        else:
            serialized_type = self.type.serialize()
        field_definition = f"{self.name}: {serialized_type}"
        if keyword.iskeyword(self.name):
            field_definition = (
                f"# {field_definition}  # This field name is a Python keyword"
            )
        return f"    {field_definition}"

    def __hash__(self) -> int:
        return hash((self.name, self.type, self.related))


@dataclasses.dataclass
class ModelData:
    """
    Represents a model dependency, this information will be used to generate
    the list of imports and inherited classes for a given model's stub
    """

    package_name: str  # Example "odoo.addons.stock.models.stock_move_line"
    module_name: str = dataclasses.field(init=False)  # Example "stock_move_line"
    odoo_model_name: str  # Example "stock.move.line"
    class_name: str = dataclasses.field(init=False)  # Example "StockMoveLine"
    source_class_name: str  # Example "StockMoveLine"
    addon_name: str  # Example "stock"
    unique_class_name: str = dataclasses.field(
        init=False
    )  # Example "StockStockMoveLine"
    inherited_model_names: Set[str]  # Example {}
    field_data_by_name: Dict[
        str,
        FieldData,
    ]  # Example {"picking_id": "stock.picking", ..., "product_qty": float, ...,  "date": datetime.datetime, ... }
    function_data_by_name: Dict[
        str,
        FunctionData,
    ]  # Example {"action_assign": FunctionData(name="action_assign", return_type=None, unknown_return_type=False, args=[FunctionArgumentData(name="self", type=None, unknown_type=True, default=None, has_default=False, is_vararg=False, is_kwarg=False)])}
    is_base_definition: bool = dataclasses.field(init=False)  # Example True
    # All the imports that are needed to define this model
    imports: Set[ImportData]
    abstract: bool
    transient: bool

    def __post_init__(self):
        """
        Assigns a unique class name based on the addon name and the model name.

        For example, the model 'stock.move.line' from the 'stock' addon has a unique
        class name 'StockStockMoveLine'.

        This enables to manipulate different implementations of the same model.
        """
        self.class_name = self.source_class_name
        self.module_name = self.package_name.rsplit(".", 1)[1]
        self.unique_class_name = _snake_case_to_pascal_case(
            self.odoo_model_name.replace(".", "_")
        )
        self.is_base_definition = self.odoo_model_name not in self.inherited_model_names

    def get_class_definition(self) -> str:
        return f"class {self.unique_class_name}:\n    pass\n"

    def get_stub_definition(
        self,
        merged_models_data_by_odoo_model_name: Dict[str, "MergedModelData"],
    ) -> Tuple[Set[str], str]:
        import_classes_to_ignore = {
            model.unique_class_name
            for model in merged_models_data_by_odoo_model_name.values()
        }
        import_lines: Set[str] = {
            import_data.serialize()
            for import_data in self.imports
            if import_data.class_name not in import_classes_to_ignore
        }
        base_class = "Model"
        if self.transient:
            base_class = "TransientModel"
        elif self.abstract:
            base_class = "AbstractModel"
        inherited_classes = [
            f'"{self.unique_class_name}"',
        ]
        field_names_to_ignore = set()
        function_names_to_ignore = set()
        for inherited_model_name in sorted(
            self.inherited_model_names - {self.odoo_model_name}
        ):
            inherited_model_data = merged_models_data_by_odoo_model_name[
                inherited_model_name
            ]
            inherited_classes.append(f'"{inherited_model_data.unique_class_name}"')
            for field_name in inherited_model_data.field_data_by_name:
                field_names_to_ignore.add(field_name)
            for function_name in inherited_model_data.function_data_by_name:
                function_names_to_ignore.add(function_name)
        class_definition = f"class {self.unique_class_name}({base_class}["
        if len(inherited_classes) == 1:
            class_definition += inherited_classes[0]
        else:
            class_definition += f"Union[{', '.join(inherited_classes)}]"
        class_definition += "]):\n"
        class_definition += self._get_class_documentation()
        class_definition += f'\n    _name = "{self.odoo_model_name}"\n'
        field_data_by_name = {
            field_name: field_data
            for field_name, field_data in self.field_data_by_name.items()
            if field_name not in field_names_to_ignore
        }
        function_data_by_name = {
            function_name: function_data
            for function_name, function_data in self.function_data_by_name.items()
            if function_name not in function_names_to_ignore
        }
        if not field_data_by_name and not function_data_by_name:
            return import_lines, class_definition
        if field_data_by_name:
            field_lines = {
                field_data.serialize(merged_models_data_by_odoo_model_name)
                for field_data in field_data_by_name.values()
            }
            class_definition += "\n" + "\n".join(sorted(field_lines)) + "\n"
        merged_models_class_names = {
            merged_models_data.unique_class_name
            for merged_models_data in merged_models_data_by_odoo_model_name.values()
        }
        escape_pattern = rf"\b({'|'.join(merged_models_class_names)})\b"
        if function_data_by_name:
            function_lines = {
                function_data.serialize(escape_pattern)
                for function_data in function_data_by_name.values()
            }
            class_definition += "\n" + "\n".join(sorted(function_lines))
        return import_lines, class_definition

    def _get_class_documentation(self) -> str:
        return ""

    def __hash__(self) -> int:
        return hash(self.unique_class_name)


@dataclasses.dataclass
class MergedModelData(ModelData):
    # All the models that were merged to create this model
    source_models: List[ModelData]

    def _get_class_documentation(self) -> str:
        documentation = '    """\n'
        documentation += f"    Merged model for {self.odoo_model_name}, built from:\n"
        source_model_names = [
            f"{source_model.package_name}.{source_model.source_class_name}"
            for source_model in self.source_models
        ]
        for source_model_name in sorted(source_model_names):
            documentation += f"        * {source_model_name}\n"
        inherited_model_names = sorted(
            self.inherited_model_names - {self.odoo_model_name}
        )
        if inherited_model_names:
            documentation += "\n    And inherits from:\n"
            for inherited_model_name in inherited_model_names:
                documentation += f"        * {inherited_model_name}\n"
        documentation += '    """\n'
        return documentation


@dataclasses.dataclass
class AddonData:
    name: str
    models_data_by_odoo_model_name: Dict[
        str,
        List[ModelData],
    ]  # All the models defined or updated in the addon, there might be some inheritance for within one module
    dependencies: Set["AddonData"]  # All the dependencies

    def __hash__(self) -> int:
        return hash(self.name)
