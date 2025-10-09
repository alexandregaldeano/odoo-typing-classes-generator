# Copyright 2025 Foodles (https://www.foodles.co/).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
import importlib
import inspect
import os
import pathlib
import shutil
import textwrap
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, ForwardRef, Generator, List, Union, get_type_hints
from unittest import mock, TestCase

from odoo_typing_classes_generator.core.generator import (
    Generator as TypingClassesGenerator,
)
from odoo_typing_classes_generator.tests.fake_module_1 import typing as models_typing


class TestGenerator(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.typing_folder_path = Path(
            "odoo_typing_classes_generator/tests/fake_module_1/typing"
        )
        cls.class_file_path = cls.typing_folder_path / "__init__.py"
        cls.stub_file_path = cls.typing_folder_path / "__init__.pyi"

    def _models_file_content(self):
        return textwrap.dedent(
            """\
            class ResCountry:
                pass


            class FakeModel1:
                pass
            """
        )

    def _reset_models_files(self):
        with open(self.class_file_path, "w") as models_file:
            models_file.write(self._models_file_content())
        if self.stub_file_path.exists():
            os.remove(self.stub_file_path)

    def setUp(self):
        self._reset_models_files()

    def tearDown(self):
        self._reset_models_files()

    @contextmanager
    def mock_open(self) -> Generator:
        with mock.patch("builtins.open") as mock_open:
            yield mock_open

    @contextmanager
    def mock_get_addon_package_name(self) -> Generator:
        def _get_addon_package_name(addon_name: str) -> str:
            if not addon_name.startswith("fake_"):
                return f"odoo.addons.{addon_name}"
            return f"odoo_typing_classes_generator.tests.{addon_name}"

        with mock.patch(
            "odoo_typing_classes_generator.core.generator."
            "Generator.get_addon_package_name",
            side_effect=_get_addon_package_name,
        ) as mock_get_addon_package_name:
            yield mock_get_addon_package_name

    @contextmanager
    def mock_get_addon_folder_path(self) -> Generator:
        def _get_addon_folder_path(addon_name: str) -> Path:
            if not addon_name.startswith("fake_"):
                return Path("odoo/addons") / addon_name
            return pathlib.Path(__file__).parent.resolve() / addon_name

        with mock.patch(
            "odoo_typing_classes_generator.core.generator."
            "Generator.get_addon_folder_path",
            side_effect=_get_addon_folder_path,
        ) as mock_get_addon_folder_path:
            yield mock_get_addon_folder_path

    def test_load_models_data(self):
        generator = TypingClassesGenerator(
            addons_path="odoo/addons/typing_classes_generator/tests",
        )
        with self.mock_get_addon_package_name(), self.mock_get_addon_folder_path():
            generator.generate("fake_module_1")
            self.assertTrue(self.class_file_path.exists())
            self.assertTrue(self.stub_file_path.exists())
            with open(self.class_file_path, "r") as models_file:
                models_file_content = models_file.read()
                self.assertEqual(self._models_file_content(), models_file_content)
            shutil.move(str(self.stub_file_path), str(self.class_file_path))
            self._test_models_typing()
        shutil.move(str(self.class_file_path), str(self.stub_file_path))

    def test_load_models_data_generate_all_classes(self):
        generator = TypingClassesGenerator(
            addons_path="odoo/addons/typing_classes_generator/tests",
            generate_all_classes=True,
        )
        with self.mock_get_addon_package_name(), self.mock_get_addon_folder_path():
            generator.generate("fake_module_1")
            self.assertTrue(self.class_file_path.exists())
            self.assertTrue(self.stub_file_path.exists())
            with open(self.class_file_path, "r") as models_file:
                models_file_content = models_file.read()
                self.assertNotEqual(self._models_file_content(), models_file_content)
            shutil.move(str(self.stub_file_path), str(self.class_file_path))
            self._test_models_typing()

    def _test_models_typing(self):
        importlib.reload(models_typing)
        module_member_names = dict(inspect.getmembers(models_typing)).keys()
        self.assertGreater(len(module_member_names), 2)
        self.assertIn("ResCountry", module_member_names)
        self.assertIn("FakeModel1", module_member_names)
        members = dict(models_typing.FakeModel1.__dict__)
        # Testing class declaration
        self.assertEqual(
            members["__orig_bases__"],
            (
                models_typing.Model[
                    Union[ForwardRef("FakeModel1"), ForwardRef("ResPartner")]
                ],
            ),
        )
        self.assertEqual(
            members["__doc__"],
            (
                "\n"
                "    Merged model for fake.model.1, built from:\n"
                "        * odoo_typing_classes_generator.tests.fake_module_1.models.fake_model_1.FakeModel1\n"
                "\n"
                "    And inherits from:\n"
                "        * res.partner\n"
                "    "
            ),
        )

        # Testing fields specific to fake.model.1
        member_annotations = members["__annotations__"]
        self.assertIn("_name", members)
        self.assertEqual(members["_name"], "fake.model.1")
        self.assertIn("a_text_field", member_annotations)
        self.assertEqual(member_annotations["a_text_field"], str)
        self.assertIn("a_related_field", member_annotations)
        self.assertEqual(member_annotations["a_related_field"], str)
        self.assertIn("a_many_to_one_field", member_annotations)
        self.assertEqual(
            member_annotations["a_many_to_one_field"],
            Union[ForwardRef("ResCompany"), bool],
        )
        self.assertIn("a_class_method", members)

        # Testing a_documented_function
        a_documented_function = members["a_documented_function"]
        self.assertNotIsInstance(a_documented_function, classmethod)
        self.assertNotIsInstance(a_documented_function, staticmethod)
        a_documented_function_hints = get_type_hints(a_documented_function)
        a_documented_function_signature = inspect.signature(a_documented_function)
        self.assertEqual(
            list(a_documented_function_signature.parameters.keys()),
            ["self", "_an_argument"],
        )
        self.assertNotIn("self", a_documented_function_hints)
        self.assertEqual(
            a_documented_function_signature.parameters["self"].default,
            inspect.Parameter.empty,
        )
        self.assertIn("_an_argument", a_documented_function_hints)
        self.assertEqual(a_documented_function_hints["_an_argument"], int)
        self.assertEqual(
            a_documented_function_signature.parameters["_an_argument"].default, 1
        )
        self.assertIn("return", a_documented_function_hints)
        self.assertEqual(
            a_documented_function_hints["return"], models_typing.ResCountry
        )

        # Testing an_undocumented_method
        an_undocumented_method = members["an_undocumented_method"]
        self.assertNotIsInstance(an_undocumented_method, classmethod)
        self.assertNotIsInstance(an_undocumented_method, staticmethod)
        an_undocumented_method_signature = inspect.signature(an_undocumented_method)
        self.assertEqual(
            list(an_undocumented_method_signature.parameters.keys()),
            ["self", "_an_argument"],
        )
        self.assertEqual(
            an_undocumented_method_signature.parameters["self"].annotation,
            inspect.Parameter.empty,
        )
        self.assertEqual(
            an_undocumented_method_signature.parameters["self"].default,
            inspect.Parameter.empty,
        )
        self.assertEqual(
            an_undocumented_method_signature.parameters["_an_argument"].annotation,
            inspect.Parameter.empty,
        )
        self.assertEqual(
            an_undocumented_method_signature.parameters["_an_argument"].default, ""
        )
        self.assertEqual(
            an_undocumented_method_signature.return_annotation,
            inspect.Parameter.empty,
        )

        # Testing a_static_method_with_default_arguments
        a_static_method_with_default_arguments = members[
            "a_static_method_with_default_arguments"
        ]
        self.assertIsInstance(a_static_method_with_default_arguments, staticmethod)
        a_static_method_with_default_arguments_signature = inspect.signature(
            a_static_method_with_default_arguments.__func__
        )
        self.assertEqual(
            list(a_static_method_with_default_arguments_signature.parameters.keys()),
            ["an_argument", "another_argument"],
        )
        self.assertEqual(
            a_static_method_with_default_arguments_signature.parameters[
                "an_argument"
            ].annotation,
            Callable[[], Any],
        )
        self.assertEqual(
            a_static_method_with_default_arguments_signature.parameters[
                "an_argument"
            ].default,
            None,
        )
        self.assertEqual(
            a_static_method_with_default_arguments_signature.parameters[
                "another_argument"
            ].annotation,
            inspect.Parameter.empty,
        )
        self.assertEqual(
            a_static_method_with_default_arguments_signature.parameters[
                "another_argument"
            ].default,
            "world",
        )
        self.assertEqual(
            a_static_method_with_default_arguments_signature.return_annotation,
            inspect.Parameter.empty,
        )

        # Testing a_static_method
        a_static_method = members["a_static_method"]
        self.assertIsInstance(a_static_method, staticmethod)
        a_static_method_hints = get_type_hints(a_static_method.__func__)
        a_static_method_signature = inspect.signature(a_static_method.__func__)
        self.assertEqual(
            list(a_static_method_signature.parameters.keys()), ["an_argument"]
        )
        self.assertIn("an_argument", a_static_method_hints)
        self.assertEqual(a_static_method_hints["an_argument"], bool)
        self.assertEqual(
            a_static_method_signature.parameters["an_argument"].default,
            inspect.Parameter.empty,
        )
        self.assertIn("return", a_static_method_hints)
        self.assertEqual(a_static_method_hints["return"], int)

        # Testing a_class_method
        a_class_method = members["a_class_method"]
        self.assertIsInstance(a_class_method, classmethod)
        a_class_method_hints = get_type_hints(a_class_method.__func__)
        a_class_method_signature = inspect.signature(a_class_method.__func__)
        self.assertEqual(
            list(a_class_method_signature.parameters.keys()), ["cls", "an_argument"]
        )
        self.assertNotIn("cls", a_class_method_hints)
        self.assertEqual(
            a_class_method_signature.parameters["cls"].default,
            inspect.Parameter.empty,
        )
        self.assertIn("an_argument", a_class_method_hints)
        self.assertEqual(a_class_method_hints["an_argument"], str)
        self.assertEqual(
            a_class_method_signature.parameters["an_argument"].default,
            inspect.Parameter.empty,
        )
        self.assertIn("return", a_class_method_hints)
        self.assertEqual(a_class_method_hints["return"], List[str])
