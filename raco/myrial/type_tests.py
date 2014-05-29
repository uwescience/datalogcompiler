"""Various tests of type safety."""
import unittest

from raco.fakedb import FakeDatabase
from raco.scheme import Scheme
from raco.myrial.myrial_test import MyrialTestCase
from raco.expression import TypeSafetyViolation
from collections import Counter


class TypeTests(MyrialTestCase):
    schema = Scheme(
        [("clong", "LONG_TYPE"),
         ("cint", "INT_TYPE"),
         ("cstring", "STRING_TYPE"),
         ("cfloat", "DOUBLE_TYPE"),
         ("cdate", "DATETIME_TYPE")])

    def setUp(self):
        super(TypeTests, self).setUp()
        self.db.ingest("public:adhoc:mytable", Counter(), TypeTests.schema)

    def test_noop(self):
        query = """
        X = SCAN(public:adhoc:mytable);
        STORE(X, OUTPUT);
        """

        self.check_scheme(query, TypeTests.schema)

    def test_invalid_eq1(self):
        query = """
        X = [FROM SCAN(public:adhoc:mytable) AS X EMIT clong=cstring];
        STORE(X, OUTPUT);
        """
        with self.assertRaises(TypeSafetyViolation):
            self.check_scheme(query, None)

    def test_invalid_eq2(self):
        query = """
        X = [FROM SCAN(public:adhoc:mytable) AS X EMIT cfloat=cdate];
        STORE(X, OUTPUT);
        """
        with self.assertRaises(TypeSafetyViolation):
            self.check_scheme(query, None)

    def test_invalid_ge(self):
        query = """
        X = [FROM SCAN(public:adhoc:mytable) AS X EMIT cfloat>=cstring];
        STORE(X, OUTPUT);
        """
        with self.assertRaises(TypeSafetyViolation):
            self.check_scheme(query, None)

    def test_invalid_lt(self):
        query = """
        X = [FROM SCAN(public:adhoc:mytable) AS X EMIT cfloat<cdate];
        STORE(X, OUTPUT);
        """
        with self.assertRaises(TypeSafetyViolation):
            self.check_scheme(query, None)

    def test_invalid_and(self):
        query = """
        X = [FROM SCAN(public:adhoc:mytable) AS X EMIT cfloat AND cdate];
        STORE(X, OUTPUT);
        """
        with self.assertRaises(TypeSafetyViolation):
            self.check_scheme(query, None)

    def test_invalid_or(self):
        query = """
        X = [FROM SCAN(public:adhoc:mytable) AS X EMIT cfloat OR cdate];
        STORE(X, OUTPUT);
        """
        with self.assertRaises(TypeSafetyViolation):
            self.check_scheme(query, None)

    def test_invalid_not(self):
        query = """
        X = [FROM SCAN(public:adhoc:mytable) AS X EMIT not cdate];
        STORE(X, OUTPUT);
        """
        with self.assertRaises(TypeSafetyViolation):
            self.check_scheme(query, None)

    def test_invalid_plus(self):
        query = """
        X = [FROM SCAN(public:adhoc:mytable) AS X EMIT cdate + cint];
        STORE(X, OUTPUT);
        """
        with self.assertRaises(TypeSafetyViolation):
            self.check_scheme(query, None)

    def test_invalid_times(self):
        query = """
        X = [FROM SCAN(public:adhoc:mytable) AS X EMIT cdate * cstring];
        STORE(X, OUTPUT);
        """
        with self.assertRaises(TypeSafetyViolation):
            self.check_scheme(query, None)

    def test_invalid_divide(self):
        query = """
        X = [FROM SCAN(public:adhoc:mytable) AS X EMIT cdate / clong];
        STORE(X, OUTPUT);
        """
        with self.assertRaises(TypeSafetyViolation):
            self.check_scheme(query, None)
