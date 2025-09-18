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
    help="Comma-separated list of Odoo modules to generate typing classes for",
    required=True,
)
@click.option(
    "--addons-path",
    required=True,
    help="Path where the modules are location, relative to the current working directory",
)
def main(modules: str, addons_path: str):
    for module in modules.split(","):
        _logger.info(f"[{module}] Generating typing classes...")
        Generator(addons_path).generate(module)
        _logger.info(f"[{module}] Done generating typing classes.")


if __name__ == "__main__":
    main()
