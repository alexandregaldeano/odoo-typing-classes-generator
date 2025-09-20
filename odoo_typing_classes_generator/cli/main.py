import logging

import click

from odoo_typing_classes_generator.core.generator import Generator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_logger = logging.getLogger(__name__)


@click.command()
@click.option(
    "--modules",
    help="Comma-separated list of Odoo modules to generate typing classes for.",
    required=True,
)
@click.option(
    "--addons-path",
    required=True,
    help="Path where the modules are located, relative to the current working directory.",
)
@click.option(
    "--stub-mode",
    is_flag=True,
    help="If set, generates stub files (.pyi) instead of regular Python files (.py).",
)
@click.option(
    "--generate-all-classes",
    is_flag=True,
    help="By default in stub mode, the models.py files with all the possible Odoo models. "
    "If not set, the models.py files will only be created if they don't exist yet "
    "and won't be modified if they already exist.",
)
def main(modules: str, addons_path: str, stub_mode: bool, generate_all_classes: bool):
    if generate_all_classes and not stub_mode:
        raise click.UsageError(
            "--generate-all-classes can only be used with --stub-mode"
        )
    for module in modules.split(","):
        _logger.info(f"[{module}] Generating typing classes...")
        Generator(addons_path, stub_mode, generate_all_classes).generate(module)
        _logger.info(f"[{module}] Done generating typing classes.")


if __name__ == "__main__":
    main()
