
from raco.catalog import FromFileCatalog
import sys

c1 = FromFileCatalog.load_from_file(sys.arv[1])
c2 = FromFileCatalog.load_from_file(sys.arv[2])
FromFileCatalog.print_cat(c1, c2)
