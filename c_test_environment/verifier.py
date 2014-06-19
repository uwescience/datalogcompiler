import re
import sys

def verify(testout, expected, ordered):
    numpat = re.compile(r'(\d+)')
    tuplepat = re.compile(r'Materialized')
    test = ({}, [])
    expect = ({}, [])

    def addTuple(tc, t):
        if ordered:
            tcl = tc[1]
            tcl.append(t)
        else:
            tcs = tc[0]
            if t not in tcs:
                tcs[t] = 1
            else:
                tcs[t]+=1

    with open(testout, 'r') as file:
        for line in file.readlines():
            m = tuplepat.search(line)
            if m:
                tlist = []
                for number in numpat.finditer(line, m.end()):
                    tlist.append(int(number.group(0)))

                t = tuple(tlist)
                addTuple(test, t)

    with open(expected, 'r') as file:
        for line in file.readlines():
            tlist = []
            for number in numpat.finditer(line):
                tlist.append(int(number.group(0)))

            t = tuple(tlist)
            addTuple(expect, t)

    print test
    print expect
    assert test == expect, "\n test:  %s !=\n expect:%s" % (test, expect)
    print "pass"


if __name__ == '__main__':
    testout=sys.argv[1]
    expected=sys.argv[2]

    ordered = False
    if len(sys.argv) > 3:
        if sys.argv[3] == 'o':
            ordered = True 

    verify(testout, expected, ordered)
 