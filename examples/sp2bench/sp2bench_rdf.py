
tr = "sp2bench_1m"
queries = {}

queries['Q1'] = """A(yr) :- %(tr)s(journal, 'rdf:type', 'bench:Journal'),
                 %(tr)s(journal, 'dc:title', 'Journal 1 (1940)'),
                 %(tr)s(journal, 'dcterms:issued', yr)"""

queries['Q2'] = """A(inproc, author, booktitle, title, proc, ee, page, url, yr, abstract) :- %(tr)s(inproc, 'rdf:type' 'bench:Inproceedings'),
   %(tr)s(inproc, 'dc:creator', author),
   %(tr)s(inproc, 'bench:booktitle', booktitle),
   %(tr)s(inproc, 'dc:title', title),
   %(tr)s(inproc, 'dcterms:partOf', proc),
   %(tr)s(inproc, 'rdfs:seeAlso', ee),
   %(tr)s(inproc, 'swrc:pages',  page),
   %(tr)s(inproc, 'foaf:homepage', url),
   %(tr)s(inproc, 'dcterms:issued', yr)"""
# TODO: make abstract optional (can do this with a union)
# TODO: order by yr

queries['Q3a'] = """A(article) :- %(tr)s(article, 'rdf:type', 'bench:Article'),
                       %(tr)s(article, property, value),
                       property = 'swrc:pages'"""

queries['Q4'] = """A(name1, name2) :- %(tr)s(article1, 'rdf:type', 'bench:Article'),
                           %(tr)s(article2, 'rdf:type', 'bench:Article'),
                           %(tr)s(article1, 'dc:creator', author1),
                           %(tr)s(author1, 'foaf:name', name1),
                           %(tr)s(article2, 'dc:creator', author2),
                           %(tr)s(author2, 'foaf:name', name2),
                           %(tr)s(article1, 'swrc:journal', journal),
                           %(tr)s(article2, 'swrc:journal', journal),
                           name1 < name2"""
# TODO be sure DISTINCT


# syntactically join with equality; 
queries['Q5a'] = """A(person, name) :- %(tr)s(article, 'rdf:type', 'bench:Article'),
                            %(tr)s(article, 'dc:creator', person),
                            %(tr)s(inproc, 'rdf:type', 'bench:Inproceedings'),
                            %(tr)s(inproc, 'dc:creator', person2),
                            %(tr)s(person, 'foaf:name', name),
                            %(tr)s(person2, 'foaf:name', name2),
                            name = name2"""
# syntactically join with naming
queries['Q5a'] = """A(person, name) :- %(tr)s(article, 'rdf:type', 'bench:Article'),
                            %(tr)s(article, 'dc:creator', person),
                            %(tr)s(inproc, 'rdf:type', 'bench:Inproceedings'),
                            %(tr)s(inproc, 'dc:creator', person),
                            %(tr)s(person, 'foaf:name', name)"""

# TODO: Q6 requires negation

# TODO: Q7 requires double negation


queries['Q8'] = """Erdoes(erdoes) :- %(tr)s(erdoes, 'rdf:type', 'foaf:Person'), 
                          %(tr)s(erdoes, 'foaf:name', "Paul Erdoes") 
        A(name) :- Erdoes(erdoes),
                   %(tr)s(doc, 'dc:creator', erdoes),
                   %(tr)s(doc, 'dc:creator', author),
                   %(tr)s(doc2, 'dc:creator', author),
                   %(tr)s(doc2, 'dc:creator', author2),
                   %(tr)s(author2, 'foaf:name', name),
                   author != erdoes, 
                   doc2 != doc, 
                   author2 != erdoes,
                   author2 != author
                     
         A(name) :- Erdoes(erdoes),
                    %(tr)s(doc, 'dc:creator', erdoes),
                    %(tr)s(doc, 'dc:creator', author), 
                    %(tr)s(author, 'foaf:name', name),
                    author != erdoes"""
#TODO be sure DISTINCT

queries['Q9'] = """A(predicate) :- %(tr)s(person, 'rdf:type', 'foaf:Person'),
                        %(tr)s(subject, predicate, person)

        A(predicate) :- %(tr)s(person, 'rdf:type', 'foaf:Person'),
                        %(tr)s(person, predicate, object)"""
#TODO be sure DISTINT


queries['Q10'] = """A(subj, pred) :- %(tr)s(subj, pred, 'person:Paul_Erdoes')"""
# Is this right? is there such a string?

queries['Q11'] = """A(ee) :- %(tr)s(publication, 'rdfs:seeAlso', ee)"""
#TODO order by, limit, offset