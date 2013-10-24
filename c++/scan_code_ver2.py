from raco import RACompiler
import raco.algebra as alg
import raco.clang as clang
import raco.boolean as rbool
from collections import deque

import logging
LOG = logging.getLogger(__name__)
   
class cpp_code :

    #constructor
    def __init__(self,physicalplan,queryname,dis=False) :
        #physical plan is a list of tuples, each containing a str and a clang operator
        self.plan = physicalplan
        self.cpp_code = ''
        self.query_name = queryname
        self.scan_count = 0
        self.node_to_name = {}
        self.node_to_hash = {}
        self.node_to_table = {}
        self.indent = 0
        self.index = 0
        self.relations = set()
        self.hashes = set()
        self.structs = set()
        self.relation_to_index = {}
        self.relation_to_tupleType = {}
        self.distinct = dis
        self.result_tuple = 'results_tuple'

    #-----------------------------------------------------------------------

    #generate code call
    def gen_code(self) :
        # generate header file
        f = open(self.query_name + '.h','w')
        f.write(self.generate_header(self.query_name))
        f.close()

        # include header file
        # TODO: this should be part of the file template
        self.emit('#include "' + self.query_name + '.h"\n\n')

        # the plan appears to so far have only one root element
        for s,c in self.plan :
            LOG.debug("s=%s c=%s",s,c)
            self.initial_walk(c)

        if self.distinct :
            self.emit(self.generate_results_tuple())

        self.emit('\n\nvoid query () {\n')
        self.indent += 4

        self.emit(self.setup_code())

        #generate_files call
        for s,c in self.plan :
            self.visit(c)

        self.emit(self.wrapup_code())

        self.emit('\n}\n\nint main() { query(); }')
        self.indent -= 4

        f = open(self.query_name + '.cpp','w')
        f.write(self.cpp_code)
        f.close()

    #-----------------------------------------------------------------------

    def generate_results_tuple(self) :
        return open('templates_ver2/results_tuple.template').read()

    #-----------------------------------------------------------------------

    def setup_code(self) :
        #for now
        return self.count_startup_code()

    #-----------------------------------------------------------------------

    def update(self) :
        #for now
        return self.count_update_code()

    #-----------------------------------------------------------------------

    def wrapup_code(self) :
        #for now
        return self.count_wrapup_code()

    #-----------------------------------------------------------------------

    def count_startup_code(self) :
        code = open('templates_ver2/count_setup.template').read()
        return code.replace('\n','\n' + ' '*self.indent) 

    #-----------------------------------------------------------------------

    def count_update_code(self) :
        code = open('templates_ver2/count_update.template').read()
        return code.replace('\n','\n' + ' '*self.indent)

    #-----------------------------------------------------------------------

    def update_distinct(self,table) :
        code = open('templates_ver2/distinct_update.template').read()
        code = code.replace('$$table$$',table)
        #index - 1 ??
        code = code.replace('$$index$$','index' + str(self.index))
        code = code.replace('$$tuple$$',self.result_tuple)
        return code.replace('\n','\n' + ' '*self.indent)

    #-----------------------------------------------------------------------

    def count_wrapup_code(self) :
        code = open('templates_ver2/count_output.template').read()
        return code.replace('\n','\n' + ' '*self.indent)  

    #-----------------------------------------------------------------------

    def emit(self, codeStr):
      self.cpp_code+=codeStr
      

    def struct_definition(self,n) :
      struct_def_template = """
struct %(relationTupleName)s {
  %(fields)s
};
"""
      LOG.debug(n)
      
      relname = n.relation_key
      t_name = relname + '_tuple'
      
      self.relation_to_tupleType[n] = t_name
      
      # if not seen relation yet then add a definition 
      if relname not in self.structs :
        self.structs.add(relname)
        numcols = len(n.scheme().attributes)
        
        declTemp = """int a%(id)s;\n  """ 
        fieldsStr = ""
        for i in range(numcols) :
          fieldsStr += declTemp % { 'id':i }
      
        self.emit(struct_def_template % { 'relationTupleName': t_name, 'fields':fieldsStr})
  

    #-----------------------------------------------------------------------

    def eliminate_non_equijoins(self,n) :
        for i in range(len(n.joinconditions)) :
            self.recursive_find_equal(n,n.joinconditions[i],i)

    def recursive_find_equal(self,n,c,i) :
        try :
            if c.literals[0] == '=' :
                n.joinconditions[i] = c
            else :
                self.recursive_find_equal(n,c.left,i)
                self.recursive_find_equal(n,c.left,i)

        except AttributeError :
            return

    #-----------------------------------------------------------------------

    #load scan template
    def gen_code_for_scan(self,n) :
        relName = n.relation_key

        if relName in self.relations :
            self.node_to_name[n] = relName
            return ''

        filename = n.relation_key #could be changed later
        numcols = len(n.scheme().attributes)
        code = open('templates_ver2/scan.template').read()
        code = code.replace('$$varname$$',relName)
        code = code.replace('$$filename$$','"' + str(filename) + '"')
        code = code.replace('$$tuple$$',self.relation_to_tupleType[n])
        #code = code.replace('$$numcolumns$$',str(numcols))
        code = code.replace('$$tmp_tuple$$','tmp_tuple' + str(self.scan_count))
        code = code.replace('$$f$$','f' + str(self.scan_count))
        #code = code.replace('$$count$$', 'count' + str(self.scan_count))
        tuple_code = ''
        for i in range(numcols) :
            tmp_code = open('templates_ver2/scan_tuple_assign.template').read()
            tmp_code = tmp_code.replace('$$f$$','f'+str(self.scan_count))
            tmp_code = tmp_code.replace('$$tmp_tuple$$','tmp_tuple' + str(self.scan_count))
            tmp_code = tmp_code.replace('$$count$$',str(i))
            tuple_code += tmp_code

        code = code.replace('$$code_to_create_tuple$$',tuple_code)
        self.node_to_name[n] = relName
        self.scan_count += 1
        self.relations.add(relName)
        return code.replace('\n','\n' + ' '*self.indent)

    #-----------------------------------------------------------------------

    #code to generate header
    def generate_header(self,query_name) :
        code = open('templates_ver2/header.template').read()
        code = code.replace('$$qn$$',query_name)
        return code.replace('\n','\n' + ' '*self.indent)

    #-----------------------------------------------------------------------

    #generate code to create hash
    def generate_hash_code(self,hashname,relation,column,n) :
        if (relation,column) in self.hashes :
            return ''

        self.hashes.add((relation,column))
        code = open('templates_ver2/hash.template').read()
        code = code.replace('$$hashname$$',hashname)
        code = code.replace('$$relation$$',relation)
        code = code.replace('$$column$$',str(column))
        code = code.replace('$$tuple$$', self.relation_to_tupleType[n])
        return code.replace('\n','\n' + ' '*self.indent)

    #-----------------------------------------------------------------------

    def generate_loop_code(self,table,column,hashname,new_table) :
        code = open('templates_ver2/nested_loop.template').read()
        code = code.replace('$$hash$$',hashname)
        code = code.replace('$$table$$',table)
        code = code.replace('$$column$$',str(column))
        code = code.replace('$$new_table$$',new_table)
        code = code.replace('$$index$$','index' + str(self.index))
        code = code.replace('$$tuple$$',self.relation_to_tupleType[hashname])
        self.index += 1
        return code.replace('\n','\n' + ' '*self.indent)

    #-----------------------------------------------------------------------

    def generate_loop_code_clause(self,table,column,hashname,new_table,clause) :
        code = open('templates_ver2/nested_loop_select.template').read()
        code = code.replace('$$hash$$',hashname)
        code = code.replace('$$table$$',table)
        code = code.replace('$$column$$',str(column))
        code = code.replace('$$new_table$$',new_table)
        code = code.replace('$$index$$','index' + str(self.index))
        code = code.replace('$$clause$$',clause)
        code = code.replace('$$tuple$$',self.relation_to_tupleType[hashname])
        self.index += 1
        return code.replace('\n','\n' + ' '*self.indent)

    #-----------------------------------------------------------------------

    def generate_outer_loop_distinct(self,hashname,column,new_table) :
        code = open('templates_ver2/distinct_outer_loop.template').read()
        code = code.replace('$$hash$$',hashname)
        code = code.replace('$$column$$',str(column))
        code = code.replace('$$index$$','index' + str(self.index))
        self.index += 1
        code = code.replace('$$tuple$$',self.relation_to_tupleType[hashname])
        code = code.replace('$$new_table$$',new_table)
        return code.replace('\n','\n' + ' '*self.indent)

    #-----------------------------------------------------------------------


    def generate_result(self,table,clause='1') :
        code = open('templates/final_select_emit.template').read()
        code = code.replace('$$index$$','index' + str(self.index))
        code = code.replace('$$table$$',table)
        code = code.replace('$$clause$$',clause)
        if self.distinct :
            code = code.replace('$$resultcall$$',self.update_distinct(table))
        else :
            code = code.replace('$$resultcall$$',self.update())
        self.index += 1
        return code.replace('\n','\n' + ' '*self.indent)

    #-----------------------------------------------------------------------

    #messy code for generating join chain code
    def generate_join_chain(self,n) :
        #step 0: output for sanity checking, remove later
        for arg in n.args :
            print arg
        print '---'

        for c in n.joinconditions :
            print c 

        #step 1: update columns in join conditions
        tot = 0
        index = {}
        for arg in n.args :
            for i in range(tot,tot+len(arg.scheme().attributes)) :
                index[i] = (i - tot,arg)
            tot += len(arg.scheme().attributes)

        #step 2: create necessary hashes
        for i in range(0,len(n.joinconditions)) :
            pos = n.joinconditions[i].right.position
            node = n.args[i+1]
            name = node.relation_key + str(pos) + '_hash'
            self.emit(self.generate_hash_code(name,node.relation_key,pos,node))
            self.node_to_hash[node] = name
            self.relation_to_tupleType[name] = self.relation_to_tupleType[node]

        first = True
        new_table=''
        #step 3: nasty code generation
        for i in range(0,len(n.joinconditions)) :
            pos = n.joinconditions[i].left.position
            column = index[pos][0]
            hashname = self.node_to_hash[n.args[i+1]]
            table = "table" + str(self.index)
            
            clause = '1'
            if first :
                    table = self.node_to_name[n.args[0]]
                    self.relation_to_index[table] = 'index' + str(self.index)
                    clause = self.handle_clause(table,n.leftconditions[0])
            else :
                self.relation_to_index[table] = 'index' + str(self.index)
                clause = self.handle_clause(table,n.rightconditions[i-1])
            self.node_to_table[n.args[i]] = table
            new_table = "table" + str(self.index + 1)
            if first and self.distinct :
                self.emit(self.generate_outer_loop_distinct(hashname,column,new_table))
                self.indent += 4
            elif clause == '1' :
                self.emit(self.generate_loop_code(table,column,hashname,new_table))
            else :
                self.emit(self.generate_loop_code_clause(table,column,hashname,new_table,clause))
            self.indent += 4
            first = False

        #step 3.1: final loop and select
        self.node_to_table[n.args[-1]] = new_table
        self.relation_to_index[new_table] = 'index' + str(self.index)
        clause = self.handle_clause(new_table,n.rightconditions[-1])
        if not rbool.isTaut(n.finalcondition) :
            clause += ' && ' + self.handle_final_cond(n.finalcondition,index)
        self.emit(self.generate_result('table' + str(self.index),clause) + '}')

        self.emit('\n')
        #step 4: close it up
        for i in range(0,len(n.joinconditions)) :
            if i == len(n.joinconditions)-1 and self.distinct :
                self.indent -= 4
                self.emit(' ' * self.indent + '}\n' + ' ' *self.indent + 'result += d_result.size();\n')
            self.indent -= 4
            self.emit(' ' * self.indent + '}\n')
        return

    #-----------------------------------------------------------------------

    #handle select clause
    def handle_clause(self,table,clause) :
        if rbool.isTaut(clause) :
            return '1'
        c = ''
        if clause.literals[0] == 'and' :
            c += '(' + self.handle_clause(table,clause.left)
            c += ' && '
            c += self.handle_clause(table,clause.right) + ')'
            return c
        elif clause.literals[0] == 'or' :
            c += '(' + self.handle_clause(table,clause.left)
            c += ' || '
            c += self.handle_clause(table,clause.right) + ')'
            return c

        if isinstance(clause.left,rbool.NumericLiteral) :
            c += clause.left.value
        elif isinstance(clause.left,rbool.PositionReference) :
            c += table + '[' + self.relation_to_index[table] + '].a' + str(clause.left.position)

        if clause.literals[0] == '=' :
            c += '=='
        else :
            c += clause.literals[0]

        if isinstance(clause.right,rbool.NumericLiteral) :
            c += clause.right.value
        elif isinstance(clause.right,rbool.PositionReference) :
            c += table + '[' + self.relation_to_index[table] + '].a' + str(clause.right.position)
        
        return c

    #-----------------------------------------------------------------------

    #if there is a final condition
    def handle_final_cond(self,clause,ind) :

        if clause.literals[0] == 'and':
            c = '(' + self.handle_final_cond(clause.left,ind)
            c += ' && '
            c += self.handle_final_cond(clause.right,ind) + ')'
            return c
        elif clause.literals[0] == 'or':
            c = '(' + self.handle_final_cond(clause.left,ind)
            c += ' || '
            c += self.handle_final_cond(clause.right,ind) + ')'
            return c

        table1 = self.node_to_table[ind[int(clause.left.position)][1]]
        table2 = self.node_to_table[ind[int(clause.right.position)][1]]
        l = ind[int(clause.left.position)][0]
        r = ind[int(clause.right.position)][0]
        c = table1 + '[' + self.relation_to_index[table1] + '].a' + str(l)
        if clause.literals[0] == '=' :
            c += '=='
        else :
            c += clause.literals[0]

        c += table2 + '[' + self.relation_to_index[table2] + '].a' + str(r)
        return c

    #-----------------------------------------------------------------------

    #recursive code to walk the tree
    def visit (self,n):
        #generate code for a scan
        if isinstance(n,alg.ZeroaryOperator) :
            if isinstance(n,alg.Scan) :
                self.emit(self.gen_code_for_scan(n))
            #else :
                #nothing?

        #nothing here yet
        elif isinstance(n,alg.UnaryOperator) :
            self.visit(n.input)

        #nothing here yet
        elif isinstance(n,alg.BinaryOperator) :
            self.visit(n.right)
            self.visit(n.left)

        #generate code for a join chain
        elif isinstance(n,alg.NaryOperator) :
            if isinstance(n,clang.FilteringNLJoinChain) :
                for arg in n.args :
                    self.visit(arg)
                self.generate_join_chain(n)

    #-----------------------------------------------------------------------      

    def initial_walk(self,n) :
        if isinstance(n,alg.ZeroaryOperator) :
            if isinstance(n,alg.Scan) :
                self.struct_definition(n)

        #nothing here yet
        elif isinstance(n,alg.UnaryOperator) :
            LOG.warning("UnaryOperator unsupported")
            self.initial_walk(n.input)

        #nothing here yet
        elif isinstance(n,alg.BinaryOperator) :
            LOG.warning("BinaryOperator unsupported")
            self.initial_walk(n.right)
            self.initial_walk(n.left)

        #generate code for a join chain
        elif isinstance(n,alg.NaryOperator) :
            if isinstance(n,clang.FilteringNLJoinChain) :
                for child in n.args :
                    LOG.debug("join chain child: %s", child)
                    self.initial_walk(child)
                # TODO handle this differently later
                self.eliminate_non_equijoins(n)
                LOG.debug('joinconds=%s',n.joinconditions)

