from typing import List

from odoo import fields, models

from odoo_typing_classes_generator.tests.fake_module_1 import typing as models_typing


class FakeModel1(models.Model):
    _name = "fake.model.1"
    _inherit = ["res.partner"]
    _module = ""

    a_text_field = fields.Text()
    a_related_field = fields.Char(related="many_to_one_field_id.name")
    a_many_to_one_field = fields.Many2one("res.company")

    def a_documented_function(self, _an_argument: int = 1) -> models_typing.ResCountry:
        return self.a_many_to_one_field.country_id

    def an_undocumented_method(self, _an_argument=""):
        return

    @staticmethod
    def a_static_method_with_default_arguments(
        an_argument=lambda: 0, another_argument="world"
    ):
        return f"[{an_argument()}] Hello {another_argument}!"

    @staticmethod
    def a_static_method(an_argument: bool) -> int:
        return 42 if an_argument else 0

    @classmethod
    def a_class_method(cls, an_argument: str) -> List[str]:
        return [cls._name, an_argument]
