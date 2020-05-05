#!/usr/bin/env python3.7
# =================================================================================================
# Copyright (C) 2019 University of Glasgow
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

import util
from typing import Optional
import xml.etree.ElementTree as ET

from protocol import *

# RFC DOM input parsers
import parsers.parser
import parsers.rfc.rfc as rfc
import parsers.rfc.rfc_txt_parser
import parsers.rfc.rfc_xml_parser
import parsers.asciidiagrams.asciidiagrams_parser

# Output formatters
import formatters.formatter
import formatters.simple_formatter
import formatters.rust_formatter

# Protocol DFS

def dfs_struct(struct: Struct, type_names:List[str]):
    for field in struct.fields:
        dfs_protocoltype(field.field_type, type_names)

def dfs_array(array: Array, type_names:List[str]):
    dfs_protocoltype(array.element_type, type_names)

def dfs_enum(enum: Enum, type_names:List[str]):
    for variant in enum.variants:
        dfs_protocoltype(variant, type_names)
    type_names.append(enum.name)
    dfs_protocoltype(enum.parse_from, type_names)
    dfs_protocoltype(enum.serialise_to, type_names)

def dfs_function(function: Function, type_names:List[str]):
    for parameter in function.parameters:
        if parameter.param_type.name not in type_names:
            dfs_protocoltype(parameter.param_type, type_names)
    if function.return_type.name not in type_names:
        dfs_protocoltype(function.return_type, type_names)

def dfs_context(context: Context, type_names:List[str]):
    for field in context.fields:
        dfs_protocoltype(field.field_type)

def dfs_protocoltype(pt: ProtocolType, type_names:List[str]):
    if type(pt) is Struct:
        dfs_struct(pt, type_names)
    elif type(pt) is Array:
        dfs_array(pt, type_names)
    elif type(pt) is Enum:
        dfs_enum(pt, type_names)
    elif type(pt) is Function:
        dfs_function(pt, type_names)
    elif type(pt) is Context:
        dfs_context(pt, type_names)
    elif pt is None:
        return
    type_names.append(pt.name)

def dfs_protocol(protocol: Protocol):
    type_names = []

    for pdu_name in protocol.get_pdu_names():
        dfs_protocoltype(protocol.get_pdu(pdu_name), type_names)

    type_names_dedupe = []

    for type_name in type_names:
        if type_name not in type_names_dedupe:
            type_names_dedupe.append(type_name)

    return type_names_dedupe



def parse_input_file( doc : util.IETF_URI ) -> Optional[rfc.RFC] : 
    content = None 
    if doc.extn == '.xml' : 
        with open( doc.get_filepath_in() , 'r') as infile : 
            raw_content = infile.read() 
            xml_tree = ET.fromstring(raw_content) 
            content = parsers.rfc.rfc_xml_parser.parse_rfc(xml_tree) 
    elif doc.extn == '.txt' : 
        with open( doc.get_filepath_in() , 'r') as infile : 
            raw_content = infile.readlines() 
            content = parsers.rfc.rfc_txt_parser.parse_rfc(raw_content)
    return content

def main():
    # Set up optional component parsers
    # TODO : Currently we have only one parser. When multiple parsers
    # for each sub-subcomponent are available, loop through them and initialise
    #dom_parser = { "asciidiagrams" : parsers.asciidiagrams.asciidiagrams_parser.AsciiDiagramsParser() }
    dom_parser = parsers.asciidiagrams.asciidiagrams_parser.AsciiDiagramsParser()
    output_formatter = {
            "simple" : (".txt", formatters.simple_formatter.SimpleFormatter()),
            "rust"   : (".rs" , formatters.rust_formatter.RustFormatter())
            }

    opt = util.parse_cmdline()
    for idx, doc in enumerate(opt.infiles):
        print(f"document [{idx}] --> {doc} --> {doc.get_filepath_in()}")
        parsed_content = parse_input_file( doc )
        if parsed_content == None :
            print(f"Error : Parsing {doc.get_filepath()} -> container = {doc}")
            continue

        protocol = dom_parser.build_protocol(  None , parsed_content )
        type_names = dfs_protocol(protocol)

        for o_fmt in opt.output_fmt :
            out_extn, formatter = output_formatter[o_fmt]
            try:
                for type_name in type_names:
                    if protocol.has_type(type_name):
                        pt = protocol.get_type(type_name)
                        if type(pt) is BitString:
                           formatter.format_bitstring(pt)
                        elif type(pt) is Struct:
                            formatter.format_struct(pt)
                        elif type(pt) is Array:
                            formatter.format_array(pt)
                        elif type(pt) is Enum:
                            formatter.format_enum(pt)
                        elif type(pt) is Context:
                            formatter.format_context(pt)
                    elif protocol.has_func(type_name):
                        formatter.format_function(protocol.get_func(type_name))
                formatter.format_protocol(protocol)
            except Exception as e:
                print(f"Error : File {doc.get_filepath_in()}: Could not format protocol with '{o_fmt}' formatter")

            output_file = doc.gen_filepath_out( opt.root_dir, out_extn)
            output_file.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            with open(output_file, "w") as out_fp:
                out_fp.write(formatter.generate_output())
                print(f"Generated {o_fmt} output :\ninput doc = {doc.get_filepath_in()},\n--- output file = {output_file}")


if __name__ == "__main__":
    main()
