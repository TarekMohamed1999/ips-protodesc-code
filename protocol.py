# =================================================================================================
# Copyright (C) 2018 University of Glasgow
# All rights reserved.
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions 
# are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# SPDX-License-Identifier: BSD-2-Clause
# =================================================================================================

from typing import Dict, List, Tuple, Optional
from protocoltypes import *
from copy import copy

import json
import re

# =================================================================================================

class Protocol:
    _types : Dict[str,Type]
    _traits: Dict[str,Trait]
    _funcs : Dict[str,Function]

    def __init__(self):
        # Define the primitive types:
        self._types = {}
        self._types["Nothing"] = Nothing()
        self._types["Boolean"] = Boolean()
        self._types["Size"]    = Size()
        # Define the standard traits:
        self._traits = {}
        self._traits["Value"] = Trait("Value", [
            Function("get", [Parameter("self", None)], None),
            Function("set", [Parameter("self", None), Parameter("value", None)], None)
        ])
        self._traits["Sized"] = Trait("Sized", [
            Function("size", [Parameter("self", None)], self.type("Size"))
        ])
        self._traits["IndexCollection"] = Trait("IndexCollection", [
            Function("get",    [Parameter("self", None), Parameter("index", self.type("Size"))], None),
            Function("set",    [Parameter("self", None), Parameter("index", self.type("Size")), Parameter("value", None)], None),
            Function("length", [Parameter("self", None)], self.type("Size"))
        ])
        self._traits["Equality"] = Trait("Equality", [
            Function("eq", [Parameter("self", None), Parameter("other", None)], self.type("Boolean")),
            Function("ne", [Parameter("self", None), Parameter("other", None)], self.type("Boolean"))
        ])
        self._traits["Ordinal"] = Trait("Ordinal", [
            Function("lt", [Parameter("self", None), Parameter("other", None)], self.type("Boolean")),
            Function("le", [Parameter("self", None), Parameter("other", None)], self.type("Boolean")),
            Function("gt", [Parameter("self", None), Parameter("other", None)], self.type("Boolean")),
            Function("ge", [Parameter("self", None), Parameter("other", None)], self.type("Boolean"))
        ])
        self._traits["BooleanOps"] = Trait("BooleanOps", [
            Function("and", [Parameter("self", None), Parameter("other", None)], self.type("Boolean")),
            Function("or",  [Parameter("self", None), Parameter("other", None)], self.type("Boolean")),
            Function("not", [Parameter("self", None)], self.type("Boolean"))
        ])
        self._traits["ArithmeticOps"] = Trait("ArithmeticOps", [
            Function("plus",    [Parameter("self", None), Parameter("other", None)], None),
            Function("minus",   [Parameter("self", None), Parameter("other", None)], None),
            Function("multiply",[Parameter("self", None)], None),
            Function("divide",  [Parameter("self", None)], None),
            Function("modulo",  [Parameter("self", None)], None)
        ])
        # Implement standard traits:
        self._types["Boolean"].implement_trait(self.trait("Value"))
        self._types["Boolean"].implement_trait(self.trait("Equality"))
        self._types["Boolean"].implement_trait(self.trait("BooleanOps"))
        self._types["Size"].implement_trait(self.trait("Value"))
        self._types["Size"].implement_trait(self.trait("Equality"))
        self._types["Size"].implement_trait(self.trait("Ordinal"))
        self._types["Size"].implement_trait(self.trait("ArithmeticOps"))
        # Define the standards functions:
        self._funcs = {}

    # =============================================================================================
    # Private helper functions:

    def _validate_irtype(self, irobj, kind):
        if irobj["construct"] != kind:
            raise TypeError("Cannot create {} from {} object".format(kind, irobj["construct"]))
        if irobj["name"] in self._types:
            raise TypeError("Cannot create type {}: already exists".format(irobj["name"]))
        if re.search(TYPE_NAME_REGEX, irobj["name"]) == None:
            raise TypeError("Cannot create type {}: malformed name".format(irobj["name"]))

    def _parse_arguments(self, args, this: Type) -> List[Argument]:
        res = []
        for arg in args:
            name_  = arg["name"]
            expr_  = self._parse_expression(arg["value"], this)
            type_  = expr_.type()
            # FIXME: what is the value?
            value_ = None
            res.append(Argument(name_, type_, value_))
        return res

    def _parse_expression(self, expr, this: Type) -> Expression:
        if not this.kind == "Struct":
            raise TypeError("Expressions can only be evaluated in context of structure types")
        if   expr["expression"] == "MethodInvocation":
            target = self._parse_expression(expr["target"], this)
            method = expr["method"]
            args   = self._parse_arguments(expr["arguments"], this)
            return MethodInvocationExpression(target, method, args)
        elif expr["expression"] == "FunctionInvocation":
            func   = self.func(expr["name"])
            args   = self._parse_arguments(expr["arguments"], this)
            return FunctionInvocationExpression(func, args)
        elif expr["expression"] == "FieldAccess":
            target = self._parse_expression(expr["target"], this)
            field  = expr["field"]
            return FieldAccessExpression(target, field)
        elif expr["expression"] == "ContextAccess":
            field  = expr["field"]
            return ContextAccessExpression(field)
        elif expr["expression"] == "IfElse":
            condition = self._parse_expression(expr["condition"], this)
            if_true   = self._parse_expression(expr["if_true"  ], this)
            if_false  = self._parse_expression(expr["if_false" ], this)
            return IfElseExpression(condition, if_true, if_false)
        elif expr["expression"] == "This":
            return ThisExpression(this)
        elif expr["expression"] == "Constant":
            type_ = self.type(expr["type"])
            value = expr["value"]
            return ConstantExpression(type_, value)
        else:
            raise TypeError("Cannot parse expression: {}".format(expr["expression"]))

    def _parse_transform(self, transform) -> Optional[Transform]:
        if transform != None:
            into_name = transform["into_name"]
            into_type = self.type(transform["into_type"])
            using     = self.func(transform["using"])
            return Transform(into_name, into_type, using)
        else:
            return None

    def _parse_fields(self, fields, this) -> List[Field]:
        res = []
        for field in fields:
            if re.search(FUNC_NAME_REGEX, field["name"]) == None:
                raise TypeError("Cannot parse field {}: malformed name".format(field["name"]))
            _name       = field["name"]
            _type       = self.type(field["type"])
            _is_present = self._parse_expression(field["is_present"], this)
            _transform  = self._parse_transform(field["transform"])
            res.append(Field(_name, _type, _is_present, _transform))
        return res

    def _parse_constraints(self, constraints, this: Type) -> List[Expression]:
        res = []
        for constraint in constraints:
            expr = self._parse_expression(constraint, this)
            if expr.type() != self.type("Boolean"):
                raise TypeError("Cannot parse constraint: {} != Boolean".format(expr.type()))
            res.append(expr)
        return res

    def _parse_actions(self, actions, this: Type) -> List[Expression]:
        res = []
        for action in actions:
            expr = self._parse_expression(action, this)
            if expr.type() != self.type("Nothing"):
                raise TypeError("Cannot parse actions: returns {} not Nothing".format(expr.type()))
            res.append(expr)
        return res

    def _parse_variants(self, variants) -> List[Type]:
        res = []
        for v in variants:
            res.append(self.type(v["type"]))
        return res

    def _parse_parameters(self, parameters) -> List[Parameter]:
        res = []
        for p in parameters:
            res.append(Parameter(p["name"], self.type(p["type"])))
        return res

    # =============================================================================================
    # Public API:

    def define_bitstring(self, irobj):
        """
        Define a new bit string type for this protocol. 
        The type constructor is described in Section 3.2.1 of the IR specification.

        Parameters:
            self  - the protocol in which the new type is defined
            irobj - a dict representing the JSON type constructor
        """
        self._validate_irtype(irobj, "BitString")
        name         = irobj["name"]
        size         = irobj["size"]
        self._types[name] = BitString(name, size)
        self._types[name].implement_trait(self.trait("Sized"))
        self._types[name].implement_trait(self.trait("Value"))
        self._types[name].implement_trait(self.trait("Equality"))

    def define_array(self, irobj):
        """
        Define a new array type for this protocol. 
        The type constructor is described in Section 3.2.2 of the IR specification.

        Parameters:
          self  - the protocol in which the new type is defined
          irobj - a dict representing the JSON type constructor
        """
        self._validate_irtype(irobj, "Array")
        name         = irobj["name"]
        element_type = self._types[irobj["element_type"]]
        length       = irobj["length"]
        self._types[name] = Array(name, element_type, length)
        self._types[name].implement_trait(self.trait("Sized"))
        self._types[name].implement_trait(self.trait("Equality"))
        self._types[name].implement_trait(self.trait("IndexCollection"))

    def define_struct(self, irobj):
        """
        Define a new structure type for this protocol. 
        The type constructor is described in Section 3.2.3 of the IR specification.

        Parameters:
          self  - the protocol in which the new type is defined
          irobj - a dict representing the JSON type constructor
        """
        self._validate_irtype(irobj, "Struct")
        name         = irobj["name"]
        self._types[name] = Struct(irobj["name"])
        for field in self._parse_fields(irobj["fields"], self._types[name]):
            self._types[name].add_field(field)
        for constraint in self._parse_constraints(irobj["constraints"], self._types[name]):
            self._types[name].add_constraint(constraint)
        for action in self._parse_actions(irobj["actions"], self._types[name]):
            self._types[name].add_action(action)
        self._types[name].implement_trait(self.trait("Sized"))
        self._types[name].implement_trait(self.trait("Equality"))

    def define_enum(self, irobj):
        """
        Define a new enumerated type for this protocol. 
        The type constructor is described in Section 3.2.4 of the IR specification.

        Parameters:
          self  - the protocol in which the new type is defined
          irobj - a dict representing the JSON type constructor
        """
        self._validate_irtype(irobj, "Enum")
        name         = irobj["name"]
        variants     = self._parse_variants(irobj["variants"])
        self._types[name] = Enum(name, variants)
        self._types[name].implement_trait(self.trait("Sized"))

    def derive_type(self, irobj):
        """
        Define a new derived type for this protocol. 
        The type constructor is described in Section 3.2.5 of the IR specification.

        Parameters:
          self  - the protocol in which the new type is defined
          irobj - a dict representing the JSON type constructor
        """
        self._validate_irtype(irobj, "NewType")
        name         = irobj["name"]
        derived_from = irobj["derived_from"]
        implements   = irobj["implements"]
        orig_type    = self.type(derived_from)
        self._types[name] = copy(orig_type)
        self._types[name].name    = name
        self._types[name].traits  = copy(orig_type.traits)
        self._types[name].methods = copy(orig_type.methods)
        for impl in irobj["implements"]:
            self._types[name].implement_trait(self.trait(impl["trait"]))

    def define_function(self, irobj):
        """
        Define a new function type for this protocol. 
        The type constructor is described in Section 3.2.6 of the IR specification.

        Parameters:
          self  - the protocol in which the new type is defined
          irobj - a dict representing the JSON type constructor
        """
        if irobj["construct"] != "Function":
            raise TypeError("Cannot create Function from {} object".format(irobj["construct"]))
        if irobj["name"] in self._funcs:
            raise TypeError("Cannot create Function {}: already exists".format(irobj["name"]))
        if re.search(FUNC_NAME_REGEX, irobj["name"]) == None:
            raise TypeError("Cannot create Function {}: malformed name".format(irobj["name"]))
        name        = irobj["name"]
        params      = self._parse_parameters(irobj["parameters"])
        return_type = self.type(irobj["return_type"])
        self._funcs[name] = Function(name, params, return_type)

    def define_context(self, irobj):
        # FIXME: implement this
        # FIXME: add trait implementations
        raise TypeError("unimplemented (define_context)")

    def type(self, type_name):
        return self._types[type_name]

    def func(self, func_name):
        return self._funcs[func_name]

    def trait(self, trait_name):
        return self._traits[trait_name]

    def typecheck(self):
        # FIXME: implement this
        raise TypeError("unimplemented (typecheck)")

# =================================================================================================
# Unit tests:

import unittest

class TestProtocol(unittest.TestCase):
    # =============================================================================================
    # Test cases for types in the IR:

    def test_define_bitstring(self):
        protocol = Protocol()
        protocol.define_bitstring({
            "construct"    : "BitString",
            "name"         : "Timestamp",
            "size"         : 32
        })
        res = protocol.type("Timestamp")
        self.assertEqual(res.kind, "BitString")
        self.assertEqual(res.name, "Timestamp")
        self.assertEqual(res.size, 32)
        # Check trait implementations:
        self.assertEqual(len(res.traits), 3)
        self.assertIn("Equality", res.traits)
        self.assertIn("Sized",    res.traits)
        self.assertIn("Value",    res.traits)
        # FIXME: add test for methods

    def test_define_array(self):
        protocol = Protocol()
        protocol.define_bitstring({
            "construct"    : "BitString",
            "name"         : "SSRC",
            "size"         : 32
        })
        protocol.define_array({
            "construct"    : "Array",
            "name"         : "CSRCList",
            "element_type" : "SSRC",
            "length"       : 4
        })
        res = protocol.type("CSRCList")
        self.assertEqual(res.kind, "Array")
        self.assertEqual(res.name, "CSRCList")
        self.assertEqual(res.element_type, protocol.type("SSRC"))
        self.assertEqual(res.length, 4)
        self.assertEqual(res.size, 128)
        # Check trait implementations:
        self.assertEqual(len(res.traits), 3)
        self.assertIn("Equality",        res.traits)
        self.assertIn("IndexCollection", res.traits)
        self.assertIn("Sized",           res.traits)
        # FIXME: add test for methods

    def test_define_struct(self):
        protocol = Protocol()
        protocol.define_bitstring({
            "construct" : "BitString",
            "name"      : "SeqNumTrans",
            "size"      : 16
        })
        protocol.define_bitstring({
            "construct" : "BitString",
            "name"      : "SeqNum",
            "size"      : 16
        })
        protocol.define_bitstring({
            "construct" : "BitString",
            "name"      : "Timestamp",
            "size"      : 32
        })
        protocol.define_function({
            "construct"   : "Function",
            "name"        : "transform_seq",
            "parameters"  : [
            {
                "name" : "seq",
                "type" : "SeqNum"
            }],
            "return_type" : "SeqNumTrans"
        })
        protocol.define_struct({
            "construct"   : "Struct",
            "name"        : "TestStruct",
            "fields"      : [
                {
                    "name"       : "seq",
                    "type"       : "SeqNum",
                    "is_present" : {
                        "expression" : "Constant",
                        "type"       : "Boolean",
                        "value"      : "True"
                    },
                    "transform"  : {
                        "into_name" : "ext_seq",
                        "into_type" : "SeqNumTrans",
                        "using"     : "transform_seq"
                    }
                },
                {
                    "name"       : "ts",
                    "type"       : "Timestamp",
                    "is_present" : {
                        "expression" : "Constant",
                        "type"       : "Boolean",
                        "value"      : "True"
                    },
                    "transform"  : None
                }
            ],
            "constraints" : [
                {
                    "expression" : "MethodInvocation",
                    "target"     : {
                        "expression" : "FieldAccess",
                        "target"     : {
                            "expression" : "This"
                        },
                        "field"     : "seq"
                    },
                    "method"     : "eq",
                    "arguments"  : [
                        {
                            "name"  : "other",
                            "value" : {
                                "expression" : "Constant",
                                "type"       : "SeqNum",
                                "value"      : 47
                            }
                        }
                    ]
                }
            ],
            # FIXME: add tests for actions
            "actions" : [
            ]
        })
        res = protocol.type("TestStruct")
        self.assertEqual(res.kind, "Struct")
        self.assertEqual(res.name, "TestStruct")
        self.assertEqual(res.fields[0].name, "seq")
        self.assertEqual(res.fields[0].type, protocol.type("SeqNum"))
        # FIXME: add test for fields[0].is_present
        # FIXME: add test for fields[0].transform
        self.assertEqual(res.fields[1].name, "ts")
        self.assertEqual(res.fields[1].type, protocol.type("Timestamp"))
        # FIXME: add test for fields[1].is_present
        # FIXME: add test for fields[1].transform
        # FIXME: add test for constraints
        # FIXME: add test for actions
        # Check trait implementations:
        self.assertEqual(len(res.traits), 2)
        self.assertIn("Equality", res.traits)
        self.assertIn("Sized",    res.traits)
        # FIXME: add test for methods

    def test_define_enum(self):
        protocol = Protocol()
        protocol.define_bitstring({
            "construct" : "BitString",
            "name"      : "TypeA",
            "size"      : 32
        })
        protocol.define_bitstring({
            "construct" : "BitString",
            "name"      : "TypeB",
            "size"      : 32
        })
        protocol.define_enum({
            "construct"   : "Enum",
            "name"        : "TestEnum",
            "variants"    : [
                {"type" : "TypeA"},
                {"type" : "TypeB"}
            ]
        })
        res = protocol.type("TestEnum")
        self.assertEqual(res.variants[0], protocol.type("TypeA"))
        self.assertEqual(res.variants[1], protocol.type("TypeB"))
        # Check trait implementations:
        self.assertEqual(len(res.traits), 1)
        self.assertIn("Sized", res.traits)
        # FIXME: add test for methods

    def test_derive_type(self):
        protocol = Protocol()
        protocol.define_bitstring({
            "construct" : "BitString",
            "name"      : "Bits16",
            "size"      : 16
        })
        protocol.derive_type({
            "construct"    : "NewType",
            "name"         : "SeqNum",
            "derived_from" : "Bits16",
            "implements"   : [{"trait" : "Ordinal"}]
        })
        res = protocol.type("SeqNum")
        self.assertEqual(res.kind, "BitString")
        self.assertEqual(res.name, "SeqNum")
        # Check trait implementations:
        self.assertEqual(len(res.traits), 4)
        self.assertIn("Equality", res.traits)
        self.assertIn("Sized",    res.traits)
        self.assertIn("Value",    res.traits)
        self.assertIn("Ordinal",  res.traits)
        # FIXME: add test for methods

    def test_define_function(self):
        protocol = Protocol()
        protocol.define_bitstring({
            "construct" : "BitString",
            "name"      : "Bits16",
            "size"      : 16
        })
        protocol.define_function({
            "construct"   : "Function",
            "name"        : "testFunction",
            "parameters"  : [
                {
                    "name" : "foo",
                    "type" : "Bits16"
                },
                {
                    "name" : "bar",
                    "type" : "Boolean"
                }
            ],
            "return_type" : "Boolean"
        })
        res = protocol.func("testFunction")
        self.assertEqual(res.name, "testFunction")
        self.assertEqual(res.parameters[0].name, "foo")
        self.assertEqual(res.parameters[0].type, protocol.type("Bits16"))
        self.assertEqual(res.parameters[1].name, "bar")
        self.assertEqual(res.parameters[1].type, protocol.type("Boolean"))
        self.assertEqual(res.return_type, protocol.type("Boolean"))

    @unittest.skip("test case not yet implemented")
    def test_define_context(self):
        # FIXME: implement test case
        pass

    # =============================================================================================
    # Test cases for expressions:

    def test_parse_expression_MethodInvocation(self):
        # Expressions must be parsed in the context of a structure type:
        protocol = Protocol()
        protocol.define_struct({
            "construct"   : "Struct",
            "name"        : "TestStruct",
            "fields"      : [],
            "constraints" : [],
            "actions"     : []
        })
        # Check we can parse MethodInvocation expressions:
        json = {
            "expression" : "MethodInvocation",
            "target"     : {
                "expression" : "This"
            },
            "method"     : "eq",
            "arguments"  : [
                {
                    "name"  : "other",
                    "value" : {
                        "expression" : "Constant",
                        "type"       : "Boolean",
                        "value"      : "False"
                    }
                }
            ]
        }
        expr = protocol._parse_expression(json, protocol.type("TestStruct"))
        self.assertTrue(isinstance(expr, MethodInvocationExpression))
        self.assertTrue(expr.type(), protocol.type("Boolean"))

    def test_parse_expression_FunctionInvocation(self):
        # Expressions must be parsed in the context of a structure type:
        protocol = Protocol()
        protocol.define_struct({
            "construct"   : "Struct",
            "name"        : "TestStruct",
            "fields"      : [],
            "constraints" : [],
            "actions"     : []
        })
        protocol.define_bitstring({
            "construct" : "BitString",
            "name"      : "Bits16",
            "size"      : 16
        })
        protocol.define_function({
            "construct"   : "Function",
            "name"        : "testFunction",
            "parameters"  : [
            {
                "name" : "foo",
                "type" : "Bits16"
            },
            {
                "name" : "bar",
                "type" : "Boolean"
            }],
            "return_type" : "Boolean"
        })
        # Check we can parse FunctionInvocation expressions:
        json = {
            "expression" : "FunctionInvocation",
            "name"       : "testFunction",
            "arguments"  : [
                {
                    "name"  : "foo",
                    "value" : {
                        "expression" : "Constant",
                        "type"       : "Bits16",
                        "value"      : 12
                    }
                },
                {
                    "name"  : "bar",
                    "value" : {
                        "expression" : "Constant",
                        "type"       : "Boolean",
                        "value"      : "False"
                    }
                }
            ]
        }
        expr = protocol._parse_expression(json, protocol.type("TestStruct"))
        self.assertTrue(isinstance(expr, FunctionInvocationExpression))
        self.assertTrue(expr.type(), protocol.type("Boolean"))

    def test_parse_expression_FieldAccess(self):
        # Expressions must be parsed in the context of a structure type:
        protocol = Protocol()
        protocol.define_bitstring({
            "construct" : "BitString",
            "name"      : "TestField",
            "size"      : 32
        })
        protocol.define_struct({
            "construct"   : "Struct",
            "name"        : "TestStruct",
            "fields"      : [{
                "name"       : "test",
                "type"       : "TestField",
                "is_present" : {
                    "expression" : "Constant",
                    "type"       : "Boolean",
                    "value"      : "True"
                },
                "transform"  : None
            }],
            "constraints" : [],
            "actions"     : []
        })
        # Check that we can parse FieldAccess expressions
        json = {
            "expression" : "FieldAccess",
            "target"     : {"expression" : "This"},
            "field"      : "test"
        }
        expr = protocol._parse_expression(json, protocol.type("TestStruct"))
        self.assertTrue(isinstance(expr, FieldAccessExpression))
        self.assertEqual(expr.type(), protocol.type("TestField"))
        self.assertEqual(expr.target.type(), protocol.type("TestStruct"))
        self.assertEqual(expr.field, "test")

    @unittest.skip("test case not yet implemented")
    def test_parse_expression_ContextAccess(self):
        # FIXME: implement test case
        pass

    def test_parse_expression_IfElse(self):
        # Expressions must be parsed in the context of a structure type:
        protocol = Protocol()
        protocol.define_struct({
            "construct"   : "Struct",
            "name"        : "TestStruct",
            "fields"      : [],
            "constraints" : [],
            "actions"     : []
        })
        # Check we can parse IfElse expressions:
        json = {
            "expression" : "IfElse",
            "condition"  : {
                  "expression" : "Constant",
                  "type"       : "Boolean",
                  "value"      : "True"
            },
            "if_true"    : {
                  "expression" : "Constant",
                  "type"       : "Boolean",
                  "value"      : "True"
            },
            "if_false"   : {
                  "expression" : "Constant",
                  "type"       : "Boolean",
                  "value"      : "False"
            },
        }
        expr = protocol._parse_expression(json, protocol.type("TestStruct"))
        self.assertTrue(isinstance(expr, IfElseExpression))
        self.assertEqual(expr.type(), protocol.type("Boolean"))
        self.assertEqual(expr.condition.type(), protocol.type("Boolean"))
        self.assertEqual(expr.if_true.type(),   protocol.type("Boolean"))
        self.assertEqual(expr.if_false.type(),  protocol.type("Boolean"))

    def test_parse_expression_This(self):
        # Expressions must be parsed in the context of a structure type:
        protocol = Protocol()
        protocol.define_struct({
            "construct"   : "Struct",
            "name"        : "TestStruct",
            "fields"      : [],
            "constraints" : [],
            "actions"     : []
        })
        # Check we can parse This expressions:
        json = {
            "expression" : "This"
        }
        expr = protocol._parse_expression(json, protocol.type("TestStruct"))
        self.assertTrue(isinstance(expr, ThisExpression))
        self.assertEqual(expr.type(), protocol.type("TestStruct"))

    def test_parse_expression_Constant(self):
        # Expressions must be parsed in the context of a structure type:
        protocol = Protocol()
        protocol.define_struct({
            "construct"   : "Struct",
            "name"        : "TestStruct",
            "fields"      : [],
            "constraints" : [],
            "actions"     : []
        })
        # Check we can parse This expressions:
        json = {
            "expression" : "Constant",
            "type"       : "Size",
            "value"      : 2
        }
        expr = protocol._parse_expression(json, protocol.type("TestStruct"))
        self.assertTrue(isinstance(expr, ConstantExpression))
        self.assertTrue(expr.type(), protocol.type("Size"))

    # =============================================================================================
    # Test cases for the overall protocol:

    @unittest.skip("test case not yet implemented")
    def test_protocol(self):
        # FIXME: add test for overall protocol definition
        pass

# =================================================================================================
if __name__ == "__main__":
    unittest.main()

# vim: set tw=0 ai:
