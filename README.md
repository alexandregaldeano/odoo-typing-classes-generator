[![Pre-commit Status](https://github.com/alexandregaldeano/odoo-typing-classes-generator/actions/workflows/pre-commit.yml/badge.svg?branch=main)](https://github.com/alexandregaldeano/odoo-typing-classes-generator/actions/workflows/pre-commit.yml?query=branch%3Amain)

# odoo-typing-classes-generator

Trying to Improve the Developer Experience
by Generating Typing Classes for Odoo Models

This is project at this stage is only a proof of concept.

For a given Odoo module, this tool scans its dependencies and introspects any classes inheriting from `odoo.models.BaseModel` in order to generate corresponding typing classes for every Odoo model.

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
