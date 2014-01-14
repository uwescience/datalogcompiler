'''
Classes for representing and manipulating Datalog programs.

In particular, they can be compiled to (iterative) relational algebra expressions.
'''
import networkx as nx
from raco import expression
import raco.algebra
import raco.scheme
import raco.catalog
from raco import relation_key

class Program(object):
    def __init__(self, rules):
        self.rules = rules
        self.compiledidbs = {}

    def isIDB(self, term):
        """Is this term also an IDB?"""
        return self.IDB(term) != []

    def IDB(self, term):
        """Return a list of rules that define an IDB corresponding to the given term: relation names are the same, and the number of columns are the same."""
        matches = []
        for r in self.rules:
            if r.IDBof(term):
                matches.append(r)

        return matches

    def compiling(self, idbterm):
        """Return true if any of the rules that define the given idb are being compiled"""
        for r in self.rules:
            if r.head.samerelation(idbterm):
                if r.compiling:
                    return True
        return False

    def intermediateRule(self, rule):
        """Return True if the head appears in the body of any other rule."""
        for other in self.rules:
            if other.refersTo(rule.head) and other.head != rule.head:
                return True
        return False

    def toRA(self):
        """Return a set of relational algebra expressions implementing this program."""
        self.idbs = {}
        for rule in self.rules:
            block = self.idbs.setdefault(rule.head.name, [])
            block.append(rule)

        newplans = [(idb, self.compileIDB(idb)) for (idb, rules) in self.idbs.items() if any([not self.intermediateRule(r) for r in rules])]

        return newplans

    def compileIDB(self, idb):
        """Compile an idb by name.  Uses the self.idbs data structure created in self.toRA"""

        if idb in self.compiledidbs:
            return self.compiledidbs[idb]
        else:
            rules = self.idbs[idb]
            plans = [r.toRA(self) for r in rules]
            ra = reduce(raco.algebra.Union, plans)
            self.compiledidbs[self] = ra
            return ra

    def __repr__(self):
        return "\n".join([str(r) for r in self.rules])

class JoinSequence(object):
    """Convenience class for operating on a sequence of joins.
  A planner takes a joingraph and emits a join sequence.
  It's not yet a relational plan; we still need to do some bookkeeping
  with respect to datalog terms"""

    def __init__(self):
        self.terms = []
        self.conditions = []
        self.num_atoms = 0

    def offset(self, term):
        """Find the position offset for columns in term.
    For example, offset([A(X,Y), B(Y,Z)], B) == 2
    and offset([A(X,Y), B(Y,Z)], A) == 0"""
        pos = 0
        for t in self.terms:
            if t == term:
                return pos
            pos = pos + len(t.valuerefs)

        raise KeyError("%s not found in join sequence %s" % (term, self.terms))

    def makePlan(self, selection_conditions, program):
        """Make a relational plan. The selection_conditions are explicit conditions from the Datalog rule, like X=3"""
        leaves = [t.makeLeaf(selection_conditions, program) for t in self.terms]

        if not leaves:
            return raco.algebra.EmptyRelation(raco.scheme.Scheme())

        leftmost = leaves[0]
        pairs = zip(self.conditions, leaves[1:])

        def makejoin(leftplan, (condition, right)):
            return raco.algebra.Join(condition, leftplan, right)

        return reduce(makejoin, pairs, leftmost)

    def addjoin(self, left, right, condition):
        """Append a join to the sequence.  The left term should already appear somewhere in the sequence."""
        if not self.terms:
            self.terms.append(left)
            self.num_atoms += len(left)

        leftoffset = self.offset(left)
        condition.leftoffset(leftoffset)
        condition.rightoffset(self.num_atoms)
        self.terms.append(right)
        self.num_atoms += len(right)
        self.conditions.append(condition)

    def __repr__(self):
        if not self.terms:
            return "EmptyJoinSequence"
        else:
            return " ".join(["%s *%s " % (t, c) for t, c in zip(self.terms, self.conditions)]) + "%s" % self.terms[-1]

    def __iter__(self):
        return self.terms.__iter__()

class Planner(object):
    """Given a join graph, produce a join sequence by choosing a join order with respect to
  some cost function.  Subclasses can implement this however they want."""

    def __init__(self, joingraph):
        self.joingraph = joingraph

    def joininfo(self, joinedge):
        """Given a join edge, return a pair of terms and the metadata for the join"""
        # TODO: Does this belong here, or in JoinSequence?  Especially the flip logic.
        leftterm, rightterm = joinedge
        data = self.joingraph.get_edge_data(*joinedge)
        condition = data["condition"]
        left, _ = data["order"]
        # We may have traversed the graph in the opposite direction
        # if so, flip the condition
        if leftterm != left:
            condition = condition.flip()
        return leftterm, rightterm, condition

    def toJoinSequence(self, edgesequence, joinsequence=None):
        """Convert a sequence of join edges to a JoinSequence object.
    A joinsequence has the correct offsets and orientation for positional references.
    An edgesequence does not."""

        if joinsequence is None: joinsequence = JoinSequence()

        # TODO: Move this to JoinSequence?
        if not edgesequence:
            return joinsequence

        left, right, condition = self.joininfo(edgesequence[0])

        joinsequence.addjoin(left, right, condition)

        js = self.toJoinSequence(edgesequence[1:], joinsequence)
        return js

def normalize(x, y):
    if y < x:
        edge = (y, x)
    else:
        edge = (x, y)
    return edge

class BFSLeftDeepPlanner(Planner):

    def chooseplan(self, costfunc=None):
        """Return a join sequence object based on the join graph.
    This one is simple -- it just adds the joins according to a breadth first search"""
        # choose first node in the original insertion order (networkx does not guarantee even a deterministic order)
        firstnode = [n for n in self.joingraph.nodes() if n.originalorder == 0][0]

        # get a BFS ordering of the edges.  Ignores costs.
        edgesequence = [x for x in nx.bfs_edges(self.joingraph, firstnode)]

        # Make it deterministic but still in BFS order
        deterministic_edge_sequence = []
        while len(edgesequence) > 0:
                # Consider all edges that have the same first node -- these are all "ties" in BFS order.
            firstx = edgesequence[0][0]
            new_edges = [(x, y) for (x, y) in edgesequence if x == firstx]
            # Sort those edges on the originalorder tuple of the source and destination
            deterministic_edge_sequence.extend(sorted(new_edges, key=lambda (x, y) : (x.originalorder, y.originalorder)))
            # Remove all those edges from edgesequence
            edgesequence = [(x, y) for (x, y) in edgesequence if x != firstx]

         # Generate a concrete sequence of terms with conditions properly adjusted
        joinsequence = self.toJoinSequence(deterministic_edge_sequence)
        return joinsequence

class Rule(object):
    def __init__(self, headbody):
        self.head = headbody[0]
        self.body = headbody[1]
        # flag used to detect recursion
        self.compiling = False
        self.fixpoint = None

    def vars(self):
        """Return a list of variables in their order of appearence in the rule.  No attempt to remove duplicates"""
        for term in self.body:
            for v in term.vars():
                yield v

    def refersTo(self, term):
        """Return true if this rule includeas a reference to the given term"""
        for bodyterm in self.body:
            if isinstance(bodyterm, Term):
                if bodyterm.samerelation(term):
                    return True
        return False

    def isParallel(self):
        if self.head.serverspec: return True
        else: return False


    def IDBof(self, term):
        """Return true if this rule defines an IDB corresponding to the given term"""
        return term.name == self.head.name and len(term.valuerefs) == len(self.head.valuerefs)

    def toRA(self, program):
        """Emit a relational plan for this rule"""
        if program.compiling(self.head):
            # recursive rule
            if not self.fixpoint:
                self.fixpoint = raco.algebra.Fixpoint()
            state = raco.algebra.State(self.head.name, self.fixpoint)
            return state
        else:
            self.compiling = True

        # get the terms, like A(X,Y,"foo")
        terms = [c for c in self.body if isinstance(c, Term)]

        # get the conditions, like Z=3
        conditions = [c for c in self.body if isinstance(c, expression.BinaryBooleanOperator)]

        # construct the join graph
        joingraph = nx.Graph()
        N = len(terms)
        for i, term1 in enumerate(terms):
            # store the order for explaining queries later -- not strictly necessary
            term1.originalorder = i

            joingraph.add_node(term1, term=term1)
            for j in range(i+1, N):
                term2 = terms[j]
                joins = term1.joinsto(term2, conditions)
                if joins:
                    conjunction = reduce(expression.AND, joins)
                    joingraph.add_edge(term1, term2, condition=conjunction, order=(term1, term2))

        # find connected components (some non-determinism in the order here)
        comps = nx.connected_component_subgraphs(joingraph)

        component_plans = []

        # for each component, choose a join order
        for component in comps:
            cycleconditions = []
            # check for cycles
            cycles = nx.cycle_basis(component)
            while cycles:
                # choose an edge to break the cycle
                # that edge will be a selection condition after the final join
                #oneedge = cycles[0][-2:]
                oneedge = sorted(cycles[0], key=lambda v: v.originalorder)[-2:]
                data = component.get_edge_data(*oneedge)
                cycleconditions.append(data)
                component.remove_edge(*oneedge)
                cycles = nx.cycle_basis(component)

            if len(component) == 1:
                # no joins to plan
                onlyterm = component.nodes()[0]
                plan = onlyterm.makeLeaf(conditions, program)
            else:
                # TODO: clean this up. joingraph -> joinsequence -> relational plan
                planner = BFSLeftDeepPlanner(component)

                joinsequence = planner.chooseplan()

                # create a relational plan, finally
                # pass in the conditions to make the leaves of the plan
                plan = joinsequence.makePlan(conditions, program)


            for condition_info in cycleconditions:
                predicate = condition_info["condition"]
                order = condition_info["order"]

                leftoffset = joinsequence.offset(order[0])
                rightoffset = joinsequence.offset(order[1])

                predicate.leftoffset(leftoffset)
                predicate.rightoffset(rightoffset)
                # create selections after each cycle
                plan = raco.algebra.Select(predicate, plan)

            component_plans.append(plan)

        # link the components with a cross product
        plan = component_plans[0]
        for newplan in component_plans[1:]:
            plan = raco.algebra.CrossProduct(plan, newplan)

        def attr(i, r, relation_alias):
            if isinstance(r, Var):
                name = r.var
                attrtype = None
            elif isinstance(r, expression.Literal):
                name = "pos%s" % i
                attrtype = type(r.value)
            return (name, attrtype)

        try:
            scheme = plan.scheme()
        except AttributeError:  #raco.algebra.RecursionError:
            scheme = raco.scheme.Scheme([attr(i, r, self.head.name) for i, r in enumerate(self.head.valuerefs)])

        # Helper function for the next two steps (TODO: move this to a method?)
        def findvar(variable):
            var = variable.var
            if var not in scheme:
                msg = "Head variable %s does not appear in rule body: %s" % (var, self)
                raise SyntaxError(msg)
            return raco.expression.UnnamedAttributeRef(scheme.getPosition(var))

        # if this Rule includes a server specification, add a partition operator
        if self.isParallel():
            if isinstance(self.head.serverspec, Broadcast):
                plan = raco.algebra.Broadcast(plan)
            if isinstance(self.head.serverspec, PartitionBy):
                positions = [findvar(v) for v in self.head.serverspec.variables]
                plan = raco.algebra.PartitionBy(positions, plan)


        # Put a project or a group by at the top of the plan

        # Resolve variable references in the head; pass through aggregate expressions
        def toAttrRef(e):
            if raco.expression.isaggregate(e):
                # assuming that every aggregate has exactly one argument
                return e.__class__(findvar(e.input))
            elif isinstance(e, Var):
                return findvar(e)
        columnlist = [toAttrRef(v) for v in self.head.valuerefs]

        # If any of the expressions in the head are aggregate expression, construct a group by
        if any([raco.expression.isaggregate(v) for v in self.head.valuerefs]):
            plan = raco.algebra.GroupBy(columnlist, plan)
        else:
            # otherwise, just build a project
            plan = raco.algebra.Project(columnlist, plan)


        # If we found a cycle, the "root" of the plan is the fixpoint operator
        if self.fixpoint:
            self.fixpoint.loopBody(plan)
            plan = self.fixpoint
            self.fixpoint = None

        self.compiling = False

        return plan

    def __repr__(self):
        return "%s :- %s" % (self.head, ", ".join([str(t) for t in self.body]))

class Var(raco.expression.Expression):
    def __init__(self, var):
        self.var = var

    def vars(self):
        """Works with BinaryBooleanOperator.vars to return a list of vars from any expression"""
        return [self.var]

    def __str__(self):
        return str(self.var)

    def __repr__(self):
        return str(self.var)

    def evaluate(self, _tuple, scheme, state=None):
        raise NotImplementedError()

    def apply(self, f):
        raise NotImplementedError()

class Term(object):
    def __init__(self, parsedterm):
        self.name = parsedterm[0]
        self.alias = self.name
        self.valuerefs = [vr for vr in parsedterm[1]]
        self.originalorder = None

    def __len__(self):
        """How many atoms are in this term"""
        return len(self.valuerefs)

    def setalias(self, alias):
        """Assign an alias for this term. Used when the same relation appears twice in one rule."""
        self.alias = alias

    def samerelation(self, term):
        """Return True if the argument refers to the same relation"""
        return self.name == term.name

    def __repr__(self):
        return "%s_%s(%s)" % (self.__class__.__name__, self.name, ",".join([str(e) for e in self.valuerefs]))

    def vars(self):
        """Return a list of variable names used in this term."""
        return [vr.var for vr in self.valuerefs if isinstance(vr, Var)]

    def varpos(self):
        """Return a list of (position, variable name) tuples for variables used in this term."""
        return [(pos, vr.var) for (pos, vr) in enumerate(self.valuerefs) if isinstance(vr, Var)]

    def joinsto(self, other, conditions):
        """Return the join conditions between this term and the argument term.  The second argument is a list of explicit conditions, like X=3 or Y=Z"""
        # get the implicit join conditions
        yourvars = other.varpos()
        myvars = self.varpos()
        joins = []
        Pos = raco.expression.UnnamedAttributeRef
        for i, var in myvars:
            match = [j for (j, var2) in yourvars if var2 == var]
            if match:
                myposition = Pos(i)
                # TODO this code only picks the first matching variable. Consider:
                #    A(x) :- R(x), S(x,x). We will end up with
                #
                #    Project($0)[Join($0=$0)[Scan(R),Select($0=$1)]Scan(S)]
                #
                # Might it be better to emit both Join conditions instead of the
                # select? In addition to the select?? Might it be better to Join on
                # the second attribute instead? TODO
                yourposition = Pos(match[0])
                joins.append(expression.EQ(myposition, yourposition))

        # get the explicit join conditions
        for c in conditions:
            if isinstance(c.left, Var) and isinstance(c.right, Var):
                # then we have a potential join condition
                if self.match(c.left) and other.match(c.right):
                    joins.append(c.__class__(self.convertvalref(c.left), other.convertvalref(c.right)))
                elif other.match(c.left) and self.match(c.right):
                    joins.append(c.__class__(other.convertvalref(c.left), self.convertvalref(c.right)))
                else:
                    # must be a condition on some other pair of relations
                    pass
        return joins

    def match(self, valref):
        """Return true if valref is a variable and is used in the list"""
        return isinstance(valref, Var) and valref.var in self.vars()

    def position(self, valueref):
        """ Returns the position of the variable in the term.  Throws an error if it does not appear."""
        return [v for v in self.vars()].index(valueref.var)

    def convertvalref(self, valueref):
        """Convert a Datalog value reference (a literal or a variable) to RA.  Literals are passed through unchanged.  Variables are converted"""
        if self.match(valueref):
            pos = self.position(valueref)
            return raco.expression.UnnamedAttributeRef(pos)
        else:
            # must be a join condition, and the other variable matches
            return valueref

    def explicitconditions(self, conditions):
        """Given a list of parsed Datalog boolean conditions, return an iterator over RA selection conditions that apply to this term.  Ignore join conditions."""
        # This method is written rather verbosely for clarity

        Literal = expression.Literal

        for condition in conditions:

            if isinstance(condition.left, Literal) and isinstance(condition.right, Literal):
                # No variables
                yield condition.__class__(condition.left, condition.right)

            elif isinstance(condition.left, Literal) and isinstance(condition.right, Var):
                # left literal, right variable, like 3 = X
                if self.match(condition.right):
                    yield condition.__class__(condition.left, self.convertvalref(condition.right))
                else:
                    # variable is not used in this term, so do nothing
                    pass

            elif isinstance(condition.left, Var) and isinstance(condition.right, Literal):
                # left variable, right literal, like X = 3
                if self.match(condition.left):
                    yield condition.__class__(self.convertvalref(condition.left), condition.right)
                else:
                    # variable is not used in this term, so do nothing
                    pass

            elif isinstance(condition.left, Var) and isinstance(condition.right, Var):
                # two variables. Both match, neither match, or one matches.
                leftmatch = self.match(condition.left)
                rightmatch = self.match(condition.right)
                if leftmatch and rightmatch:
                    # a selection condition like A(X,Y), X=Y
                    yield condition.__class__(self.convertvalref(condition.left), self.convertvalref(condition.right))
                elif not leftmatch and not rightmatch:
                    # nothing to do with this term
                    pass
                elif not leftmatch and rightmatch:
                    # join condition, leave it alone
                    pass
                elif leftmatch and not rightmatch:
                    # join condition, leave it alone
                    pass

    def implicitconditions(self):
        """An iterator over implicit selection conditions derived from the datalog syntax.
    For example, A(X,X) implies position0 == position1, and A(X,4) implies position1 == 4"""
        # Check for implicit literal equality conditions, like A(X,"foo")
        for i, b in enumerate(self.valuerefs):
            if isinstance(b, expression.Literal):
                posref = raco.expression.UnnamedAttributeRef(i)
                yield expression.EQ(posref, b)

        # Check for repeated variable conditions, like A(X,X)
        N = len(self.valuerefs)
        for i, x in enumerate(self.valuerefs):
            if isinstance(x, Var):
                for j in range(i + 1, N):
                    y = self.valuerefs[j]
                    if isinstance(y, Var):
                        # TODO: probably want to implement __eq__, but it makes Var objects unhashable
                        if x.var == y.var:
                            leftpos = raco.expression.UnnamedAttributeRef(i)
                            rightpos = raco.expression.UnnamedAttributeRef(j)
                            yield expression.EQ(leftpos, rightpos)

    def renameIDB(self, plan):
        """Rename the attributes of the plan to match the current rule. Used when chaining multiple rules."""
        term = self

        # Do we know the actual scheme? If it's recursive, we don't
        # So derive it from the rule head
        # Not really satisfied with this.
        try:
            sch = plan.scheme()
        except raco.algebra.RecursionError:
            sch = raco.scheme.Scheme([attr(i, r, term.name) for i, r in enumerate(term.valuerefs)])

        oldscheme = [name for (name, _) in sch]
        termscheme = [expr for expr in term.valuerefs]

        if len(oldscheme) != len(termscheme):
            raise TypeError("Rule with head %s does not match Term %s" % (term.name, term))

        pairs = zip(termscheme, oldscheme)

        # Merge the old and new schemes.  Use new where we can.
        def choosename(new, old):
            if isinstance(new, Var):
                # Then use this new var as the column name
                return new.var
            else:
                # It's an implicit selection condition, like R(x,3). In R's schema,
                # don't call the column name '3' (new), instead call it whatever the column
                # name was in the prior rule where R is the head variable R (old).
                return old

        mappings = [(choosename(new, old), raco.expression.UnnamedAttributeRef(i)) for i, (new, old) in enumerate(pairs)]

        # Use an apply operator to implement the renaming
        plan = raco.algebra.Apply(mappings, plan)

        return plan

    def makeLeaf(term, conditions, program):
        """Return an RA plan that Scans the appropriate relation and applies all selection conditions
      Two sources of conditions: the term itself, like A(X,"foo") -> Select(pos1="foo", Scan(A))
      and separate condition terms, like A(X,Y), X=3 -> Select(pos0=3, Scan(A))
      separate condition terms are passed in as an argument.
      """
        def attr(i, r, relation_alias):
            if isinstance(r, Var):
                name = r.var
                attrtype = None
            elif isinstance(r, expression.Literal):
                name = "pos%s" % i
                attrtype = type(r.value)
            return (name, attrtype)
            #return AttributeSpec(relation_alias, name, attrtype)

        # Chain rules together
        if program.isIDB(term):
            plan = program.compileIDB(term.name)
            scan = term.renameIDB(plan)
        else:
            # TODO: A call to some catalog?
            sch = raco.scheme.Scheme([attr(i, r, term.name) for i, r in enumerate(term.valuerefs)])
            rel_key = relation_key.RelationKey.from_string(term.name)
            scan = raco.algebra.Scan(rel_key, sch)
            scan.trace("originalterm", "%s (position %s)" % (term, term.originalorder))

        # collect conditions within the term itself, like A(X,3) or A(Y,Y)
        implconds = list(term.implicitconditions())

        # collect explicit conditions, like A(X,Y), Y=2
        explconds = list(term.explicitconditions(conditions))

        allconditions = implconds + explconds

        if allconditions:
            conjunction = reduce(expression.AND, allconditions)
            plan = raco.algebra.Select(conjunction, scan)
        else:
            plan = scan

        plan.set_alias(term)
        return plan

class IDB(Term):
    def __init__(self, termobj, serverspec=None, timestep=None):
        if timestep:
            self.name = "%s_%s" % (termobj.name, timestep.spec)
        else:
            self.name = termobj.name
        self.valuerefs = termobj.valuerefs
        self.serverspec = serverspec
        self.timestep = timestep

class EDB(Term):
    pass

class ServerSpecification(object):
    pass

class Broadcast(ServerSpecification):
    pass

class PartitionBy(ServerSpecification):
    def __init__(self, variables):
        self.variables = variables

class Timestep(object):
    def __init__(self, spec):
        self.spec = spec
        pass
