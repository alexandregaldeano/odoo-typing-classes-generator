import ast
import datetime
import importlib
import inspect
import logging
import textwrap
from collections import defaultdict
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    Union,
    get_type_hints,
)

from odoo import fields, models

from .models import (
    AddonData,
    FieldData,
    FunctionArgumentData,
    FunctionData,
    ImportData,
    MergedModelData,
    ModelData,
    TypeData,
)

_logger = logging.getLogger(__name__)


class Generator:
    python_type_by_odoo_field_type = {
        "date": datetime.date,
        "datetime": datetime.datetime,
        "time": datetime.time,
        "binary": bytes,
        "integer": int,
        "char": str,
        "text": str,
        "selection": str,
        "html": str,
        "serialized": str,
        "job_serialized": str,
        "float": float,
        "monetary": float,
        "boolean": bool,
        "many2one_reference": int,
        "reference": str,
    }

    def __init__(self, addons_path: str, generate_all_classes: bool = False):
        self.addons_path = Path(addons_path)
        self.generate_all_classes = generate_all_classes

        self.assets_path = Path(__file__).parent.parent / "assets"

        self.models_data_by_odoo_model_name: Dict[str, List[ModelData]] = defaultdict(
            list
        )
        self.addon_data_by_name: Dict[str, AddonData] = {}
        self.related_fields_to_resolve_by_odoo_model_name: Dict[
            str,
            Set[str],
        ] = defaultdict(set)
        self.modules_to_scan = {"models", "wizards"}
        self.merged_models_data_by_odoo_model_name: Dict[str, MergedModelData] = {}
        self.fields_to_ignore: Set[str] = set()
        self.functions_to_ignore: Set[str] = set()
        for module in [models.AbstractModel, models.Model, models.TransientModel]:
            self.fields_to_ignore |= {
                field_name
                for field_name, field in inspect.getmembers(module)
                if not (
                    (field_name.startswith("__") and field_name.endswith("__"))
                    or inspect.isfunction(field)
                    or inspect.ismethod(field)
                )
            }
            self.functions_to_ignore |= {
                function_name
                for function_name, _function in inspect.getmembers(
                    module,
                    lambda member: (
                        inspect.isfunction(member) or inspect.ismethod(member)
                    ),
                )
            }

    def generate(self, addon_name: str):
        # List of models.Model defined in the addon
        _addon_data = self._load_models_data(addon_name)
        # Create the merged ModelData for each Odoo model
        self._merge_models_data(addon_name)
        # Resolve the related fields
        self._resolve_related_fields(addon_name)
        # Create the stubs
        self._generate_stubs(addon_name)

    def _load_models_data(self, addon_name: str) -> AddonData:
        # This addon has already been processed, nothing to do
        if addon_name in self.addon_data_by_name:
            return self.addon_data_by_name[addon_name]
        _logger.info(f"[{addon_name}] Loading all models data")
        addon_data = AddonData(
            name=addon_name,
            models_data_by_odoo_model_name=defaultdict(list),
            dependencies=set(),
        )
        self.addon_data_by_name[addon_name] = addon_data

        addon_package_name = self.get_addon_package_name(addon_name)
        addon_module = importlib.import_module(addon_package_name)
        self._load_models_data_in_module(addon_name, addon_data, addon_module)
        if addon_name == "base":
            return addon_data

        manifest_path = Path(addon_module.__file__).parent / "__manifest__.py"
        with open(manifest_path) as manifest_file:
            manifest_content = manifest_file.read()
        manifest = ast.literal_eval(manifest_content)
        addon_dependencies = set(manifest.get("depends", []))
        addon_dependencies.add("base")
        for addon_dependency in addon_dependencies:
            addon_data.dependencies.add(self._load_models_data(addon_dependency))
        return addon_data

    def _load_models_data_in_module(
        self,
        addon_name: str,
        addon_data: AddonData,
        module: Any,
    ):
        for _model_name, model in inspect.getmembers(
            module, Generator.is_member_odoo_model
        ):
            package_name = module.__name__
            odoo_model_name = Generator.get_odoo_model_name(model)
            if not odoo_model_name:
                continue
            model_data = self._get_model_data(
                addon_name,
                package_name,
                odoo_model_name,
                model,
            )
            self.models_data_by_odoo_model_name[odoo_model_name].append(model_data)
            addon_data.models_data_by_odoo_model_name[odoo_model_name].append(
                model_data
            )
        check_submodules = inspect.getfile(module).endswith("/__init__.py")
        for _member_name, member in inspect.getmembers(module, inspect.ismodule):
            try:
                member_file_path = inspect.getfile(member)
            except:  # noqa: S112,E722
                continue
            if (
                str(self.get_addon_folder_path(addon_name)) in member_file_path
                and check_submodules
            ):
                self._load_models_data_in_module(addon_name, addon_data, member)

    def _get_model_data(
        self,
        addon_name: str,
        package_name: str,
        odoo_model_name: str,
        model: type,
    ) -> ModelData:
        _logger.info(
            f"[{addon_name}, {odoo_model_name}] Processing class {model.__class__.__module__}.{model.__name__}"
        )
        model_data = ModelData(
            package_name=package_name,
            odoo_model_name=odoo_model_name,
            source_class_name=model.__name__,
            addon_name=addon_name,
            inherited_model_names=set(Generator.get_inherits(model)),
            field_data_by_name={},
            function_data_by_name={},
            imports=set(),
            abstract=model._abstract,
            transient=model._transient,
        )
        # TODO handle non-Odoo fields and properties
        for field_name, field in inspect.getmembers(
            model,
            Generator.is_member_odoo_field,
        ):
            if field_name in self.fields_to_ignore:
                continue
            field_data = self._get_field_data(
                odoo_model_name,
                field_name,
                field,
            )
            if not field_data:
                continue
            if (
                field_data.type
                and not isinstance(field_data.type, str)
                and field_data.type.value
                in (datetime.date, datetime.datetime, datetime.time)
            ):
                model_data.imports.add(
                    ImportData(
                        package_name="datetime",
                        class_name=field_data.type.value.__name__,
                        alias=None,
                    )
                )
            model_data.field_data_by_name[field_name] = field_data
        for function_name, function in inspect.getmembers(
            model, Generator.is_member_function
        ):
            if function_name in self.functions_to_ignore:
                continue
            # We want to ignore name-mangled functions
            if not function_name.endswith("__") and "__" in function_name:
                continue
            _logger.debug(f"Processing {model_data.source_class_name}.{function_name}")
            function_data = FunctionData(
                name=function_name,
                args=[],
            )
            hints = get_type_hints(function)
            if "return" in hints:
                function_data.type = TypeData(hints["return"])
                model_data.imports |= function_data.type.imports

            attr = inspect.getattr_static(
                model,
                function_name,
            )
            function_data.is_class_method = isinstance(attr, classmethod)
            function_data.is_static_method = isinstance(attr, staticmethod)
            # Gets the unbound function to get the correct signature
            if hasattr(function, "__func__"):
                signature = inspect.signature(function.__func__)
            else:
                signature = inspect.signature(function)
            for arg_index, (arg_name, arg) in enumerate(signature.parameters.items()):
                if arg.annotation is not inspect.Parameter.empty:
                    function_argument_data = FunctionArgumentData(
                        name=arg_name,
                        type=TypeData(hints.get(arg_name)),
                    )
                    model_data.imports |= function_argument_data.type.imports
                else:
                    function_argument_data = FunctionArgumentData(
                        name=arg_name,
                        type=None,
                    )
                if inspect.isfunction(arg.default):
                    # If the default is a function, we don't know its type
                    function_argument_data.default = None
                    function_argument_data.has_default = True
                    if function_argument_data.type is None:
                        default_signature = inspect.signature(arg.default)
                        default_arg_type: List[type] = [
                            Any for _ in default_signature.parameters
                        ]
                        function_argument_data.type = TypeData(
                            Callable[default_arg_type, Any]
                        )
                    model_data.imports |= function_argument_data.type.imports
                elif arg.default is not inspect.Parameter.empty:
                    function_argument_data.default = arg.default
                    function_argument_data.has_default = True
                    default_class = arg.default.__class__
                    model_data.imports |= TypeData.collect_imports(default_class)
                if arg.kind == inspect.Parameter.VAR_POSITIONAL:
                    function_argument_data.is_vararg = True
                elif arg.kind == inspect.Parameter.VAR_KEYWORD:
                    function_argument_data.is_kwarg = True
                function_data.args.append(function_argument_data)
            model_data.function_data_by_name[function_name] = function_data
        return model_data

    def _get_field_data(
        self,
        odoo_model_name: str,
        field_name: str,
        field: fields.Field,
    ) -> Optional[FieldData]:
        field_data = FieldData(name=field_name, type="", related=None)
        field_class = field.__class__.__name__
        if isinstance(field, (fields.Many2one, fields.One2many, fields.Many2many)):
            if "related" in field.args:
                self.related_fields_to_resolve_by_odoo_model_name[odoo_model_name].add(
                    field.args["related"]
                )
                return None
            if "comodel_name" not in field.args:
                return None
            field_data.type = field.args["comodel_name"]
            return field_data
        if field.type not in self.python_type_by_odoo_field_type:
            _logger.warning(
                "Field %s with type %s is not supported",
                field_name,
                field_class,
            )
            return None
        field_data.type = TypeData(self.python_type_by_odoo_field_type[field.type])
        return field_data

    @staticmethod
    def get_addon_package_name(addon_name: str) -> str:
        return f"odoo.addons.{addon_name}"

    def get_addon_folder_path(self, addon_name: str) -> Path:
        return self.addons_path / addon_name

    def _merge_models_data(self, addon_name: str) -> None:
        package_name = f"{self.get_addon_package_name(addon_name)}.typing.models"
        for odoo_model_name, models_data in self.models_data_by_odoo_model_name.items():
            _logger.info(f"[{addon_name}, {odoo_model_name}] Merging all models data")
            merged_model_data = MergedModelData(
                package_name=package_name,
                odoo_model_name=odoo_model_name,
                source_class_name="",
                addon_name=addon_name,
                inherited_model_names={odoo_model_name},
                field_data_by_name={},
                function_data_by_name={},
                imports=set(),
                source_models=[],
                abstract=False,
                transient=False,
            )
            for model_data in sorted(models_data, key=lambda m: m.package_name):
                if model_data.is_base_definition:
                    merged_model_data.source_class_name = model_data.source_class_name
                    merged_model_data.class_name = model_data.class_name
                    merged_model_data.abstract = model_data.abstract
                    merged_model_data.transient = model_data.transient
                merged_model_data.field_data_by_name.update(
                    model_data.field_data_by_name
                )
                merged_model_data.inherited_model_names |= (
                    model_data.inherited_model_names
                )
                for (
                    function_name,
                    function_data,
                ) in model_data.function_data_by_name.items():
                    if function_name not in merged_model_data.function_data_by_name:
                        merged_model_data.function_data_by_name[
                            function_name
                        ] = function_data
                        continue
                    merged_function_data = merged_model_data.function_data_by_name[
                        function_name
                    ]
                    if merged_function_data.type:
                        merged_function_data.type = function_data.type
                    for merged_arg in merged_function_data.args:
                        if merged_arg.type:
                            continue
                        arg = next(
                            (
                                arg
                                for arg in function_data.args
                                if (arg.name == merged_arg.name and arg.type)
                            ),
                            False,
                        )
                        if not arg:
                            continue
                        merged_arg.type = arg.type
                merged_model_data.field_data_by_name.update(
                    model_data.field_data_by_name
                )
                merged_model_data.imports.update(model_data.imports)
                merged_model_data.source_models.append(model_data)
            self.merged_models_data_by_odoo_model_name[
                odoo_model_name
            ] = merged_model_data

    @classmethod
    def get_odoo_model_name(cls, model: Any) -> Optional[str]:
        if model._name:
            return model._name
        inherits = Generator.get_inherits(model)
        if not inherits:
            return None
        return inherits[0]

    @classmethod
    def get_inherits(cls, model: Any) -> List[str]:
        if not hasattr(model, "_inherit"):
            return []
        inherit: Union[str, List[str]] = model._inherit or []
        if isinstance(inherit, str):
            return [inherit]
        return inherit

    @classmethod
    def is_member_odoo_model(cls, member: Any) -> bool:
        return inspect.isclass(member) and issubclass(member, models.AbstractModel)

    @classmethod
    def is_member_odoo_field(cls, member: Any) -> bool:
        return issubclass(member.__class__.__class__, fields.MetaField)

    @classmethod
    def is_member_function(cls, member: Any) -> bool:
        return inspect.isfunction(member) or inspect.ismethod(member)

    def _resolve_related_fields(self, addon_name: str) -> None:
        _logger.info(f"[{addon_name} Resolving all the related fields")
        related_fields_to_resolve_before: Set[str] = set()
        related_fields_to_resolve = {
            f'"{odoo_model_name}".{field_name}'
            for odoo_model_name, field_names in self.related_fields_to_resolve_by_odoo_model_name.items()
            for field_name in field_names
        }
        while related_fields_to_resolve != related_fields_to_resolve_before:
            related_fields_to_resolve_before = set(related_fields_to_resolve)
            for (
                odoo_model_name,
                related_fields,
            ) in self.related_fields_to_resolve_by_odoo_model_name.items():
                model_data = self.merged_models_data_by_odoo_model_name[odoo_model_name]
                for field_name in related_fields:
                    field_key = f'"{odoo_model_name}".{field_name}'
                    if field_key not in related_fields_to_resolve:
                        continue
                    if field_name not in model_data.field_data_by_name:
                        continue
                    field_data = model_data.field_data_by_name[field_name]
                    field_type = self._resolve_related_field(model_data, field_data)
                    if field_type:
                        field_data.field_type = field_type
                        related_fields_to_resolve.remove(
                            f'"{odoo_model_name}".{field_name}'
                        )

    def _resolve_related_field(
        self, model_data: MergedModelData, field_data: FieldData
    ) -> Optional[Union[type, str]]:
        if field_data.type:
            return field_data.type
        related_field_name, related_subfield_name = field_data.related.split(".", 1)
        related_field_data = model_data.field_data_by_name[related_field_name]
        related_model_data = self.merged_models_data_by_odoo_model_name[
            related_field_name
        ]
        while related_subfield_name:
            if not related_field_data.type:
                # This field is also related, we need to resolve it first
                return None
            related_field_data = related_model_data.field_data_by_name[
                related_field_name
            ]
            (
                related_field_name,
                related_subfield_name,
            ) = related_subfield_name.related.split(".", 1)
            related_model_data = self.merged_models_data_by_odoo_model_name[
                related_field_name
            ]
        return related_field_data.type

    def _generate_stubs(self, addon_name: str) -> None:
        _logger.info(f"[{addon_name}] Generating the stubs")
        typing_folder = self.get_addon_folder_path(addon_name) / "typing"
        typing_folder.mkdir(parents=False, exist_ok=True)

        models_path = typing_folder / "__init__.py"
        if self.generate_all_classes:
            with open(models_path, "w") as models_file:
                models_file.write(self._generate_class_file_content())
        elif not models_path.exists():
            with open(models_path, "w") as models_file:
                models_file.write(
                    textwrap.dedent(
                        """\
                    # Add below the classes you want to use for typing,
                    # see the documentation for more information

                    """
                    )
                )

        models_stubs_path = typing_folder / "__init__.pyi"
        with open(models_stubs_path, "w") as models_stubs_file:
            models_stubs_file.write(self._generate_stub_file_content())

    def _generate_class_file_content(self) -> str:
        class_file_content = textwrap.dedent(
            """\
            # This file is auto-generated by Odoo Typing Classes Generator


            """
        )
        all_class_definitions = [
            merged_model_data.get_class_definition()
            for merged_model_data in self.merged_models_data_by_odoo_model_name.values()
        ]
        class_file_content += "\n\n".join(sorted(all_class_definitions))
        return class_file_content

    def _generate_stub_file_content(self) -> str:
        with open(self.assets_path / "template.pyi", "r") as template_stub_file:
            stub_file_content = template_stub_file.read()
        all_import_lines: Set[str] = set()
        all_stub_definitions: List[str] = []
        model_class_names: Set[str] = set()
        for merged_model_data in self.merged_models_data_by_odoo_model_name.values():
            model_class_names.add(merged_model_data.unique_class_name)
            import_lines, stub_definition = merged_model_data.get_stub_definition(
                self.merged_models_data_by_odoo_model_name
            )
            all_import_lines.update(import_lines)
            all_stub_definitions.append(stub_definition)
        stub_file_content = stub_file_content.replace(
            "# odoo-typing-classes-generator: imports-insertion-point",
            "\n".join(sorted(all_import_lines)) + "\n",
        )
        stub_file_content = stub_file_content.replace(
            "# odoo-typing-classes-generator: classes-insertion-point",
            "\n\n".join(sorted(all_stub_definitions)),
        )
        return stub_file_content
