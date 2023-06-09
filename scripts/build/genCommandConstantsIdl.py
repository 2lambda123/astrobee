#!/usr/bin/env python
# Copyright (c) 2017, United States Government, as represented by the
# Administrator of the National Aeronautics and Space Administration.
#
# All rights reserved.
#
# The Astrobee platform is licensed under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with the
# License. You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""
A library and command-line tool for generating a RAPID-style CommandConstants.idl
file from an XPJSON schema.
"""

import argparse
import logging
import os
import sys

# hack to ensure xgds_planner2 submodule is at head of PYTHONPATH
ffroot = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

sys.path.insert(0, os.path.join(ffroot, "astrobee", "commands", "xgds_planner2"))

import xpjsonAstrobee

TEMPLATE_MAIN = """
/*
 * Copyright (c) 2015 United States Government as represented by the
 * Administrator of the National Aeronautics and Space Administration.
 * All Rights Reserved.
 */

#include "BaseTypes.idl"

/**
 * \\file
 *
 * \\brief AstrobeeCommandConstants.idl extends the RAPID CommandConstants.idl file
 * with Astrobee-specific commands.
 *
 * \\details Refer to RAPID CommandConstants.idl for interpretation.
 *
 * \\ingroup idlfiles
 */
module rapid {
  module ext {
    module astrobee {
%(body)s
    };
  };
};
"""
# END TEMPLATE_MAIN

TEMPLATE_NOTES = """
      //@copy-declaration /** %s */
"""[
    1:-1
]

TEMPLATE_CATEGORY_DECL = """
      const rapid::String32 %(commandCategoryUpper)s = "%(commandCategory)s";
"""[
    1:-1
]

TEMPLATE_METHOD_DECL = """
      const rapid::String32 %(commandCategoryUpper)s_METHOD_%(commandIdAllCaps)s = "%(commandId)s";
"""[
    1:-1
]

TEMPLATE_PARAM_DECL = """
      const rapid::String32 %(commandCategoryUpper)s_METHOD_%(commandIdAllCaps)s_PARAM_%(paramIdAllCaps)s = "%(paramId)s";
      const rapid::DataType %(commandCategoryUpper)s_METHOD_%(commandIdAllCaps)s_DTYPE_%(paramIdAllCaps)s = rapid::%(paramValueTypeRapid)s;
"""[
    1:-1
]

TEMPLATE_CHOICE_DECL = """
      const rapid::String32 %(paramCategoryAllCaps)s_%(paramIdAllCaps)s_%(choiceLabelAllCaps)s = "%(choiceCode)s";
"""[
    1:-1
]

seenCategories = {}


def getCommandCategory(cmd):
    assert "." in cmd.id, "CommandSpec without category: %s" % cmd
    category, baseId = cmd.id.split(".", 1)
    return category


def getCategoryContext(cmd):
    category = getCommandCategory(cmd)
    return {
        "commandCategory": category,
        "commandCategoryUpper": category.upper(),
    }


def getCommandContext(cmd):
    assert "." in cmd.id, "CommandSpec without category: %s" % cmd
    category, baseId = cmd.id.split(".", 1)
    return {
        "commandId": baseId,
        "commandIdAllCaps": xpjsonAstrobee.allCaps(baseId),
        "commandCategoryUpper": category.upper(),
    }


def getParamContext(param):
    if "." in param.id:
        category, baseId = param.id.split(".", 1)
    else:
        category, baseId = None, param.id
    result = {
        "paramId": xpjsonAstrobee.fixName(baseId),
        "paramIdAllCaps": xpjsonAstrobee.allCaps(xpjsonAstrobee.fixName(baseId)),
        "paramValueTypeRapid": xpjsonAstrobee.XPJSON_PARAM_VALUE_TYPE_MAPPINGS[
            param.valueType
        ],
    }
    if category is not None:
        result["paramCategoryAllCaps"] = xpjsonAstrobee.allCaps(category)
    return result


def getNotesComment(obj):
    if obj.notes:
        return TEMPLATE_NOTES % obj.notes + "\n"
    else:
        return ""


def getChoiceContext(choiceCode, choiceLabel):
    return {
        "choiceCode": choiceCode,
        "choiceLabelAllCaps": xpjsonAstrobee.allCaps(choiceLabel),
    }


def genCommandSpecDecls(cmd):
    # don't make a declaration for RAPID-native commands; they are declared
    # in the RAPID CommandConstants.idl
    if getattr(cmd, "isRapidNative", None):
        return ""

    resultList = []

    if not getCommandCategory(cmd) in seenCategories:
        seenCategories[getCommandCategory(cmd)] = True
        categoryCtx = getCategoryContext(cmd)
        resultList += [TEMPLATE_CATEGORY_DECL % categoryCtx, "\n\n"]

    commandCtx = getCommandContext(cmd)
    resultList += [getNotesComment(cmd), TEMPLATE_METHOD_DECL % commandCtx, "\n\n"]
    for param in cmd.params:
        ctx = commandCtx.copy()
        ctx.update(getParamContext(param))
        resultList += [getNotesComment(param), TEMPLATE_PARAM_DECL % ctx, "\n\n"]
    return "".join(resultList)


def genParamDecls(param):
    if not param.choices:
        return ""

    assert "." in param.id, "ParamSpec without category: %s" % param
    paramCtx = getParamContext(param)
    resultList = []
    for choiceCode, choiceLabel in param.choices:
        ctx = paramCtx.copy()
        ctx.update(getChoiceContext(choiceCode, choiceLabel))
        resultList.append(TEMPLATE_CHOICE_DECL % ctx + "\n")
    resultList.append("\n")
    return "".join(resultList)


def genCommandConstants(inSchemaPath, outCommandConstantsPath):
    schema = xpjsonAstrobee.loadDocument(inSchemaPath)

    commandSpecs = sorted(schema.commandSpecs, key=lambda spec: spec.id)
    paramSpecs = sorted(schema.paramSpecs, key=lambda spec: spec.id)

    commandDecls = [genCommandSpecDecls(spec) for spec in commandSpecs]
    paramDecls = [genParamDecls(spec) for spec in paramSpecs]
    body = "".join(commandDecls + paramDecls)

    with open(outCommandConstantsPath, "w") as outStream:
        outStream.write(TEMPLATE_MAIN % {"body": body})
    logging.info("wrote command constants to %s", outCommandConstantsPath)


class CustomFormatter(
    argparse.RawDescriptionHelpFormatter, argparse.ArgumentDefaultsHelpFormatter
):
    pass


def main():
    parser = argparse.ArgumentParser(
        description=__doc__ + "\n\n",
        formatter_class=CustomFormatter,
    )
    parser.add_argument(
        "inSchemaPath",
        help="input XPJSON schema path",
    )
    parser.add_argument(
        "outCommandConstantsPath",
        help="output IDL command constants path",
        nargs="?",
        default="AstrobeeCommandConstants.idl",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG, format="%(message)s")
    genCommandConstants(args.inSchemaPath, args.outCommandConstantsPath)


if __name__ == "__main__":
    main()
