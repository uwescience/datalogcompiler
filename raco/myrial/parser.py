#!/usr/bin/env python

import ply.yacc as yacc

import raco.myrial.scanner as scanner

import collections
import sys

class JoinColumnCountMismatchException(Exception):
    pass

class ParseException(Exception):
    pass

# ID is a symbol name; columns is list containing either column names
# (as strings) or integer offsets (starting at zero).
JoinTarget = collections.namedtuple('JoinTarget',['id', 'columns'])

class RelationKey(object):
    def __init__(self, table, program='default', user='nobody'):
        self.table = table
        self.program = program
        self.user = user

    def __repr__(self):
        return 'RelationKey(%s,%s,%s)' % (self.table, self.program,self.user)

class Parser:
    def __init__(self, log=yacc.PlyLogger(sys.stderr)):
        self.log = log
        self.tokens = scanner.tokens

    def p_statement_list(self, p):
        '''statement_list : statement_list statement
                          | statement'''
        if len(p) == 3:
            p[0] = p[1] + [p[2]]
        else:
            p[0] = [p[1]]

    def p_statement_assign(self, p):
        'statement : ID EQUALS expression SEMI'
        p[0] = ('ASSIGN', p[1], p[3])

    def p_statement_dump(self, p):
        'statement : DUMP ID SEMI'
        p[0] = ('DUMP', p[2])

    def p_statement_describe(self, p):
        'statement : DESCRIBE ID SEMI'
        p[0] = ('DESCRIBE', p[2])

    def p_statement_explain(self, p):
        'statement : EXPLAIN ID SEMI'
        p[0] = ('EXPLAIN', p[2])

    def p_statement_dowhile(self, p):
        'statement : DO statement_list WHILE expression SEMI'
        p[0] = ('DOWHILE', p[2], p[4])

    def p_expression_id(self, p):
        'expression : ID'
        p[0] = ('ALIAS', p[1])

    def p_expression_scan(self, p):
        'expression : SCAN relation_key'
        p[0] = ('SCAN', p[2])

    def p_relation_key(self, p):
        'relation_key : LBRACE string_arg_list RBRACE'
        # {table [, program] [,user]}
        if len(p[2]) < 1:
            raise ParseException("No table name provided")
        if len(p[2]) > 3:
            raise ParseException("Too many arguments to relation key")
        p[0] = RelationKey(*p[2])

    def p_string_arg_list(self, p):
        '''string_arg_list : string_arg_list COMMA string_arg
                           | string_arg'''
        if len(p) == 4:
            p[0] = p[1] + [p[3]]
        else:
            p[0] = [p[1]]

    def p_string_arg(self, p):
        '''string_arg : ID
                      | STRING_LITERAL'''
        # For operators that take string-like arguments: allow unquoted
        # identifiers and quoted strings to be used equivalently
        p[0] = p[1]

    def p_expression_limit(self, p):
        'expression : LIMIT ID COMMA INTEGER_LITERAL'
        p[0] = ('LIMIT', p[2], p[4])

    def p_expression_distinct(self, p):
        'expression : DISTINCT expression'
        p[0] = ('DISTINCT', p[2])

    def p_expression_binary_set_operation(self, p):
        'expression : setop ID COMMA ID'
        p[0] = (p[1], p[2], p[4])

    def p_setop(self, p):
        '''setop : INTERSECT
                 | DIFF
                 | UNION'''
        p[0] = p[1]

    def p_expression_join(self, p):
        'expression : JOIN join_argument COMMA join_argument'
        if len(p[2].columns) != len(p[4].columns):
            raise JoinColumnCountMismatchException()
        p[0] = ('JOIN', p[2], p[4])

    def p_join_argument_list(self, p):
        'join_argument : ID BY LPAREN column_arg_list RPAREN'
        p[0] = JoinTarget(p[1], p[4])

    def p_join_argument_single(self, p):
        'join_argument : ID BY column_arg'
        p[0] = JoinTarget(p[1], (p[3],))

    def p_column_arg_list(self, p):
        '''column_arg_list : column_arg_list COMMA column_arg
                           | column_arg'''
        if len(p) == 4:
            cols = p[1] + [p[3]]
        else:
            cols = [p[1]]
        p[0] = cols

    def p_column_arg_string(self, p):
        'column_arg : string_arg'
        p[0] = p[1]

    def p_column_arg_offset(self, p):
        'column_arg : DOLLAR INTEGER_LITERAL'
        p[0] = p[2]

    def parse(self, s):
        parser = yacc.yacc(module=self, debug=True)
        return parser.parse(s, lexer=scanner.lexer, tracking=True)

    def p_error(self, p):
        self.log.error("Syntax error: %s" %  str(p))
