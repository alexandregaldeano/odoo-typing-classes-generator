import logging

import click
import click_odoo

from odoo_typing_classes_generator.core.generator import Generator

_logger = logging.getLogger(__name__)


@click.command()
@click.argument("module", required=True)
@click.argument("addons_path", required=True)
@click_odoo.env_options()
def main(env, module: str, addons_path: str):
    _logger.info(f"[{module}] Generating typing classes...")
    Generator(addons_path).generate(module)
    _logger.info(f"[{module}] Done generating typing classes.")


if __name__ == "__main__":
    main()
