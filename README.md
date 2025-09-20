[![Pre-commit Status](https://github.com/alexandregaldeano/odoo-typing-classes-generator/actions/workflows/pre-commit.yml/badge.svg?branch=main)](https://github.com/alexandregaldeano/odoo-typing-classes-generator/actions/workflows/pre-commit.yml?query=branch%3Amain)

# odoo-typing-classes-generator

Trying to Improve the Developer Experience
by Generating Typing Classes for Odoo Models

This is project at this stage is only a proof of concept.

For a given Odoo module, this tool scans its dependencies and introspects any classes inheriting from
`odoo.models.BaseModel` in order to generate corresponding typing classes for every Odoo model.

## Installation

```bash
$ uv sync
$ source .venv/bin/activate
$ pip install -e .
$ odoo-typing-classes-generator --help
```

## Usage: Generating the Typing Classes

```bash
$ odoo-typing-classes-generator --modules=foobar --addons-path=odoo/addons
```

This command will create the following files within the `odoo/addons/foobar` folder:

- `typing/`
  - `__init__.py`;
  - `base.py`: containing the three base Model classes in Odoo;
  - `base.pyi`: containing the detailed definitions;
  - `models.py`: either empty, or only containing the classes names depending on options; and
  - `models.pyi`: containing the detailed definitions of all Odoo models based on the module and its dependencies.

### [Required] `--modules TEXT`

Comma-separated list of Comma-separated list of Odoo modules to generate the typing classes for.

### [Required] `--addons-path TEXT`

Path where the modules are located, relative to the
current working directory.

### [Flag] `--generate-all-classes`

When set, the `typing/models.py` files will be created with all the available classes.
This is useful if you want to have all the classes available for typing, even if you don't use them all.

Warning: this can create a very large file, depending on the number of models in the module and its dependencies.

By default, the `typing/models.py` files will be created empty if they don't exist yet.

You will have to manually add the classes you want to use for typing, in the format:

```
class ClassName:
    pass
```

You can check in the models.pyi to see the available classes, all of them have a field `_name = "[Odoo Model Name]"` you can search for.
Alternatively, if you have an Odoo model `abc.def_ghi`, the typing class name will be `AbcDefGhi`.

Note: You should most likely avoid to put the stub files into your VCS.

## Usage: Use the Typing Classes In Code

It is very important to import the `typing.models` module for this to work (see reasons below).
You can, of course, use an alias to avoid name collisions.

For example:

```python
from odoo import models

from odoo.addons.foobar.typing import models as odoo_typing

class ResPartner(models.Model):
    _inherit = "res.partner"

    def test(self, companies: odoo_typing.ResCompany) -> odoo_typing.ResUsers:
        ...
```

Warning: if you import the typing class directly from the `typing.models` module,
you will have no autocomplete suggestion from your IDE\*.

\*I don't know why this is the case, plus I only tested this script with `IntelliJ IDEA 2025.2.1 (Ultimate Edition)`, if you have an explanation, you can add it here, thanks! ❤️

### In Case of Missing Classes in the `typing/models.py` File

#### Without the `--generate-all-classes` Option

You can just add them manually.
If the autocomplete still doesn't work for one or more classes,
check if they are present in the stub file.
If they are absent, check if you have missing dependencies in your manifest.

#### With the `--generate-all-classes` Option

Check if you have missing dependencies in your manifest.

## General Process

1. Scan the module and all its dependencies recursively by reading the manifest files, while doing that every time we find an Odoo model, we collect the following information:
   - whether the model is abstract, transient or concrete;
   - the list of inherited models;
   - all defined Odoo fields;
   - all the non-private / named-mangled methods and functions with their signatures;
   - for basic fields we map them to built in types;
   - for the related fields we only store the "related" value; and
   - for other fields referencing another Odoo model, we only store the model name;
2. then, for each Odoo model, we aggregate all the definitions: the list of inherited models, the list of fields, the list of functions and methods;
3. then, the type of all related fields is resolved; and
4. finally, we write the typing classes into a file.
