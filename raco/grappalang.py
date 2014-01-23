# TODO: To be refactored into parallel shared memory lang,
# where you plugin in the parallel shared memory language specific codegen

from raco import algebra
from raco import expression
from raco import catalog
from raco.language import Language
from raco import rules
from raco.utility import emitlist
from raco.pipelines import Pipelined

import logging
from algebra import gensym
LOG = logging.getLogger(__name__)

import os.path

template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "grappa_templates")

def readtemplate(fname):
    return file(os.path.join(template_path, fname)).read()


base_template = readtemplate("base_query.template")
initialize, querydef_init, finalize = base_template.split("// SPLIT ME HERE")

class GrappaLanguage(Language):
    @classmethod
    def new_relation_assignment(cls, rvar, val):
        return """
    %s
    %s
    """ % (cls.relation_decl(rvar), cls.assignment(rvar, val))

    @classmethod
    def relation_decl(cls, rvar):
        return "GlobalAddress<Tuple> %s;" % rvar

    @classmethod
    def assignment(cls, x, y):
        return "%s = %s;" % (x, y)

    @staticmethod
    def initialize(resultsym):
        return  initialize % locals()
      
    @staticmethod
    def body(compileResult, resultsym):
      code, decls = compileResult
      querydef_init_filled = querydef_init % locals()
      return emitlist(decls)+querydef_init_filled+code

    @staticmethod
    def finalize(resultsym):
        return  finalize % locals()

    @staticmethod
    def log(txt):
        return  """LOG(INFO) << "%s";\n""" % txt
    
    @staticmethod
    def log_unquoted(code): 
      return """LOG(INFO) << %s;\n""" % code

    @staticmethod
    def comment(txt):
        return  "// %s\n" % txt

    @classmethod
    def compile_stringliteral(cls, s):
        #raise ValueError("String Literals not supported in C language: %s" % s)
        return """string_lookup("%s")""" % s

    @classmethod
    def negation(cls, input):
        return "(!%s)" % (input,)

    @classmethod
    def boolean_combine(cls, args, operator="&&"):
        opstr = " %s " % operator
        conjunc = opstr.join(["(%s)" % cls.compile_boolean(arg) for arg in args])
        LOG.debug("conjunc: %s", conjunc)
        return "( %s )" % conjunc

    @classmethod
    def compile_attribute(cls, expr):
        if isinstance(expr, expression.NamedAttributeRef):
            raise TypeError("Error compiling attribute reference %s. C compiler only support unnamed perspective.  Use helper function unnamed." % expr)
        if isinstance(expr, expression.UnnamedAttributeRef):
            symbol = expr.tupleref.name
            position = expr.position # NOTE: this will only work in Selects right now
            return '%s.get(%s)' % (symbol, position)

class GrappaOperator (Pipelined):
    language = GrappaLanguage
    
class MemoryScan(algebra.Scan, GrappaOperator):
  def produce(self):
    code = ""
    #generate the materialization from file into memory
    #TODO split the file scan apart from this in the physical plan

    #TODO for now this will break whatever relies on self.bound like reusescans
    #Scan is the only place where a relation is declared
    resultsym = gensym()
    
    # now generate the scan from memory
    inputsym = resultsym

# scan from index
#    memory_scan_template = """forall_localized( %(inputsym)s_index->vs, %(inputsym)s_index->nv, [](int64_t ai, Vertex& a) {
#      forall_here_async<&impl::local_gce>( 0, a.nadj, [=](int64_t start, int64_t iters) {
#      for (int64_t i=start; i<start+iters; i++) {
#        auto %(tuple_name)s = a.local_adj[i];
#          
#          %(inner_plan_compiled)s
#       } // end scan over %(inputsym)s (for)
#       }); // end scan over %(inputsym)s (forall_here_async)
#       }); // end scan over %(inputsym)s (forall_localized)
#       """

    memory_scan_template = """
forall_localized( %(inputsym)s.data, %(inputsym)s.numtuples, [=](int64_t i, %(tuple_type)s& %(tuple_name)s) {
%(inner_plan_compiled)s
}); // end  scan over %(inputsym)s 
"""

    rel_decl_template = """Relation<%(tuple_type)s> %(resultsym)s;"""
    
    stagedTuple = StagedTupleRef(inputsym, self.scheme())

    tuple_type_def = stagedTuple.generateDefition()
    tuple_type = stagedTuple.getTupleTypename()
    tuple_name = stagedTuple.name

    # generate code for actual IO and materialization in memory
    code += FileScan(self.relation_key, self._scheme).compileme(resultsym, tuple_type)
    
    # generate declaration of the in-memory relation
    rel_decl = rel_decl_template % locals()

    inner_plan_compiled, inner_decls = self.parent.consume(stagedTuple, self)

    code += memory_scan_template % locals()
    return code, [tuple_type_def,rel_decl]+inner_decls
    
  def consume(self, t, src):
    assert False, "as a source, no need for consume"
    
    

class FileScan(algebra.Scan):

    def compileme(self, resultsym, tuple_typename):
        # TODO use the identifiers (don't split str and extract)
        LOG.debug('compiling file scan for relation_key %s' % self.relation_key)
        name = str(self.relation_key).split(':')[2]


        #tup = (resultsym, self.originalterm.originalorder, self.originalterm)
        #self.trace("// Original query position of %s: term %s (%s)" % tup)
        
        #TODO: manage the concurrent synchronization objects
        
        # graph-specific file scan
        ascii_scan_template_GRAPH = """
          {
            tuple_graph tg;
            tg = readTuples( "%(name)s" );
            
            FullEmpty<GlobalAddress<Graph<Vertex>>> f1;
            privateTask( [&f1,tg] {
              f1.writeXF( Graph<Vertex>::create(tg, /*directed=*/true) );
            });
            auto l_%(resultsym)s_index = f1.readFE();
            
            on_all_cores([=] {
              %(resultsym)s_index = l_%(resultsym)s_index;
            });
        }
        """
        
        ascii_scan_template = """
        {
        auto t = readTuples<%(tuple_typename)s>( "%(name)s", 30);
        Relation<%(tuple_typename)s> l_%(resultsym)s;
        l_%(resultsym)s.data = t;
        l_%(resultsym)s.numtuples = 30;
        on_all_cores([=]{ %(resultsym)s = l_%(resultsym)s; });
        }
        """

        if isinstance(self.relation_key, catalog.ASCIIFile):
            code = ascii_scan_template % locals()
        else:
            LOG.info("binary not currently supported for GrappaLanguage, emitting ascii")
            code = ascii_scan_template % locals()

        return code
      
    def __str__(self):
      return "%s(%s)" % (self.opname(), self.relation_key)


def getTaggingFunc(t):
  """ 
  Return a visitor function that will tag 
  UnnamedAttributes with the provided TupleRef
  """

  def tagAttributes(expr):
    # TODO non mutable would be nice
    if isinstance(expr, expression.UnnamedAttributeRef):
      expr.tupleref = t

    return None
  
  return tagAttributes



class HashJoin(algebra.Join, GrappaOperator):
  _i = 0

  @classmethod
  def __genHashName__(cls):
    name = "hash_%03d" % cls._i;
    cls._i += 1
    return name
  
  def produce(self):
    if not isinstance(self.condition, expression.EQ):
      msg = "The C compiler can only handle equi-join conditions of a single attribute: %s" % self.condition
      raise ValueError(msg)
    
    self._hashname = self.__genHashName__()
    self.outTuple = StagedTupleRef(gensym(), self.scheme())
    
    self.right.childtag = "right"
    code_right, decls_right = self.right.produce()
    init_template = """%(hashname)s.init_global_DHT( &%(hashname)s, 64 );""" 
    setro_template = """%(hashname)s.set_RO_global( &%(hashname)s );"""
    hashname = self._hashname
    code_right = (init_template%locals()) + code_right + setro_template%locals()
    
    self.left.childtag = "left"
    code_left, decls_left = self.left.produce()

    return code_right+code_left, decls_right+decls_left
  
  def consume(self, t, src):
    if src.childtag == "right":
      declr_template =  """typedef MatchesDHT<int64_t, %(in_tuple_type)s, identity_hash> DHT_%(in_tuple_type)s;
      DHT_%(in_tuple_type)s %(hashname)s;
      """
      
      right_template = """%(hashname)s.insert(%(keyname)s.get(%(keypos)s), %(keyname)s);
      """   
      
      hashname = self._hashname
      keyname = t.name
      keypos = self.condition.right.position-len(self.left.scheme())
      
      out_tuple_type_def = self.outTuple.generateDefition()
      self.rightTuple = t #TODO: this induces a right->left dependency
      in_tuple_type = self.rightTuple.getTupleTypename()

      # declaration of hash map
      hashdeclr =  declr_template % locals()
      
      # materialization point
      code = right_template % locals()
      
      return code, [out_tuple_type_def,hashdeclr]
    
    if src.childtag == "left":
      left_template = """
      %(hashname)s.lookup_iter( %(keyname)s.get(%(keypos)s), [=](%(right_tuple_type)s& %(right_tuple_name)s) {
        %(out_tuple_type)s %(out_tuple_name)s = combine<%(out_tuple_type)s, %(keytype)s, %(right_tuple_type)s> (%(keyname)s, %(right_tuple_name)s);
        %(inner_plan_compiled)s
      });
    """

      hashname = self._hashname
      keyname = t.name
      keytype = t.getTupleTypename()
      keypos = self.condition.left.position
      
      right_tuple_type = self.rightTuple.getTupleTypename()
      right_tuple_name = self.rightTuple.name

      # or could make up another name
      #right_tuple_name = StagedTupleRef.genname() 

      out_tuple_type = self.outTuple.getTupleTypename()
      out_tuple_name =self.outTuple.name
      
      inner_plan_compiled, inner_plan_declrs = self.parent.consume(self.outTuple, self)
      
      code = left_template % locals()
      return code, inner_plan_declrs

    assert False, "src not equal to left or right"
      


def compile_filtering_join(joincondition, leftcondition, rightcondition):
    """return code for processing a filtering join"""


def indentby(code, level):
    indent = " " * ((level + 1) * 6)
    return "\n".join([indent + line for line in code.split("\n")])



# iteration  over table + insertion into hash table with filter
hash_build_template = """
// build hash table for %(hashedsym)s, column %(position)s
hash_table_t<uint64_t, uint64_t> %(hashedsym)s_hash_%(position)s;
for (uint64_t  %(hashedsym)s_row = 0; %(hashedsym)s_row < %(hashedsym)s->tuples; %(hashedsym)s_row++) {
  if (%(condition)s) {
    insert(%(hashedsym)s_hash_%(position)s, %(hashedsym)s, %(hashedsym)s_row, %(position)s);
  }
}
"""

# iteration over table + lookup
# name of tuple output is r{depth}
# note the the rightcondition, is the condition in the build phase
nested_hash_join_first_template = """
for (uint64_t  %(leftsym)s_row = 0; %(leftsym)s_row < %(leftsym)s->tuples; %(leftsym)s_row++) {
  if (%(leftcondition)s) {
    for (Tuple<uint64_t> r%(depth)s : lookup(%(rightsym)s_hash_%(rightposition)s, %(leftsym)s, %(leftposition)s)) {
      %(inner_plan_compiled)s
    } // end join of %(leftsym)s[%(leftposition)s] and %(rightsym)s[%(rightposition)s]
  } // end filter %(depth)s
} // end scan over %(leftsym)s
"""

# lookup tuple
nested_hash_join_rest_template = """
if (%(leftcondition)s) {
  for (Tuple<uint64_t> r%(depth)s : lookup(%(rightsym)s_hash_%(rightposition)s, r%(depthMinusOne)s, %(leftposition)s) {
    %(inner_plan_compiled)s
  }
}
"""
    


#def neededDownstream(ops, expr):
#  if expr in ops:
#
#
#
#class FreeMemory(GrappaOperator):
#  def fire(self, expr):
#    for ref in noReferences(expr)

      
# TODO:
# The following is actually a staged materialized tuple ref.
# we should also add a staged reference tuple ref that just has relationsymbol and row  
class StagedTupleRef:
  nextid = 0
  
  @classmethod
  def genname(cls):
    x = cls.nextid
    cls.nextid+=1
    return "t_%03d" % x
  
  def __init__(self, relsym, scheme):
    self.name = self.genname()
    self.relsym = relsym
    self.scheme = scheme
    self.__typename = None
  
  def getTupleTypename(self):
    if self.__typename==None:
      fields = ""
      relsym = self.relsym
      for i in range(0, len(self.scheme)):
        fieldnum = i
        fields += "_%(fieldnum)s" % locals()
        
      self.__typename = "MaterializedTupleRef_%(relsym)s%(fields)s" % locals()
    
    return self.__typename

    
  def generateDefition(self):
    fielddeftemplate = """int64_t _fields[%(numfields)s];
    """
    copytemplate = """_fields[%(fieldnum)s] = rel->relation[row*rel->fields + %(fieldnum)s];
    """
    template = """
          // can be just the necessary schema
  class %(tupletypename)s {
    private:
    %(fielddefs)s
    %(padding)s
    
    public:
    int64_t get(int field) const {
      return _fields[field];
    }
    
    void set(int field, int64_t val) {
      _fields[field] = val;
    }
    
    int numFields() const {
      return %(numfields)s;
    }
    
    %(tupletypename)s (std::vector<int64_t> vals) {
      for (int i=0; i<vals.size(); i++) _fields[i] = vals[i];
    }
    
    %(tupletypename)s () {
      // no-op
    }
    
    std::ostream& dump(std::ostream& o) const {
      o << "Materialized(";
      for (int i=0; i<numFields(); i++) {
        o << _fields[i] << ",";
      }
      o << ")";
      return o;
    }
  };
  std::ostream& operator<< (std::ostream& o, const %(tupletypename)s& t) {
    return t.dump(o);
  }

  """
    getcases = ""
    setcases = ""
    copies = ""
    numfields = len(self.scheme)
    fielddefs = fielddeftemplate % locals()
    
    # hack to get tuples to divide evenly into grappas BLOCK_SIZE
    grappa_block_size = 64 # sizeof(int64_t)*8
    padding_map = { 1: 0, 2: 0, 3: 1, 4: 0, 5: 3, 6: 2, 7: 1, 8: 0}
    assert numfields <= 8
    padding_amt = padding_map[numfields]
    if padding_amt > 0: padding = """// pad to grappa BLOCK_SIZE 
    char _padding[8*%s];"""%padding_map[numfields]
    else: padding = ""
    
    # TODO: actually list the trimmed schema offsets
    for i in range(0, numfields):
      fieldnum = i
      copies += copytemplate % locals()

    tupletypename = self.getTupleTypename()
    relsym = self.relsym
      
    code = template % locals()
    return code
  


class BasicSelect(algebra.Select, GrappaOperator):
  def produce(self):
    return self.input.produce()
    
  def consume(self, t, src):
    basic_select_template = """if (%(conditioncode)s) {
%(inner_code_compiled)s
}"""

    # tag the attributes with references
    # TODO: use an immutable approach instead (ie an expression Visitor for compiling)
    [_ for _ in self.condition.postorder(getTaggingFunc(t))]
    
    # compile the predicate into code
    conditioncode = GrappaLanguage.compile_boolean(self.condition)
    
    inner_code_compiled, inner_decls = self.parent.consume(t, self)
    
    code = basic_select_template % locals()
    return code, inner_decls
    
class swapJoinSides(rules.Rule):
  # swaps the inputs to a join
  def fire(self, expr):
    if isinstance(expr,algebra.Join):
      return algebra.Join(expr.condition, expr.right, expr.left)
    else:
      return expr

class GrappaAlgebra(object):
    language = GrappaLanguage

    operators = [
    #FileScan,
    MemoryScan,
    BasicSelect,
    HashJoin
  ]
    rules = [
     #rules.OneToOne(algebra.Join,TwoPassHashJoin),
    rules.removeProject(),
    rules.CrossProduct2Join(),
    #swapJoinSides(),
#    FilteringNestedLoopJoinRule(),
#    FilteringHashJoinChainRule(),
#    LeftDeepFilteringJoinChainRule(),
    rules.OneToOne(algebra.Select,BasicSelect),
 #   rules.OneToOne(algebra.Select,TwoPassSelect),
    rules.OneToOne(algebra.Scan,MemoryScan),
    rules.OneToOne(algebra.Join,HashJoin),
  #  rules.FreeMemory()
  ]