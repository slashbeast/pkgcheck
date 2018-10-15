from itertools import chain

from pkgcore.ebuild.const import VCS_ECLASSES

from pkgcheck.test import misc
from pkgcheck.dropped_keywords import DroppedKeywordsReport as drop_keys


class TestDroppedKeywords(misc.ReportTestCase):

    check_kls = drop_keys

    def mk_pkg(self, ver, keywords='', eclasses=()):
        return misc.FakePkg(
            f"dev-util/diffball-{ver}",
            data={
                "KEYWORDS": keywords,
                "_eclasses_": eclasses,
            })

    def test_it(self):
        # single version, shouldn't yield.
        check = drop_keys(
            misc.Options((("arches", ["x86", "amd64"]),), verbose=None),
            None)
        self.assertNoReport(check, [self.mk_pkg('1')])
        reports = self.assertReports(
            check, [self.mk_pkg("1", "x86 amd64"), self.mk_pkg("2")])
        assert set(chain.from_iterable(x.arches for x in reports)) == set(["x86", "amd64"])

        # ensure it limits itself to just the arches we care about
        # check unstable at the same time;
        # finally, check '-' handling; if x86 -> -x86, that's valid.
        self.assertNoReport(
            check,
            [self.mk_pkg("1", "x86 ~amd64 ppc"),
             self.mk_pkg("2", "~amd64 x86"),
             self.mk_pkg("3", "-amd64 x86")])

        # check added keyword handling
        self.assertNoReport(
            check,
            [self.mk_pkg("1", "amd64"),
             self.mk_pkg("2", "x86"),
             self.mk_pkg("3", "~x86 ~amd64")])

        # check special keyword handling
        for key in ('-*', '*', '~*'):
            self.assertNoReport(
                check,
                [self.mk_pkg("1", "x86 ~amd64"),
                self.mk_pkg("2", key)])

        # ensure it doesn't flag live ebuilds
        for eclass in VCS_ECLASSES:
            self.assertNoReport(
                check,
                [self.mk_pkg("1", "x86 amd64"),
                self.mk_pkg("9999", "", eclasses=(eclass,))])

    def test_verbose_mode(self):
        # verbose mode outputs a report per version with dropped keywords
        check = drop_keys(
            misc.Options((("arches", ["x86", "amd64"]),), verbose=1),
            None)
        reports = self.assertReports(
            check,
            [self.mk_pkg("1", "x86 amd64"),
             self.mk_pkg("2"),
             self.mk_pkg("3")])
        assert len(reports) == 2
        assert set(x.version for x in reports) == set(["2", "3"])

    def test_regular_mode(self):
        # regular mode outputs the most recent pkg with dropped keywords
        check = drop_keys(
            misc.Options((("arches", ["x86", "amd64"]),), verbose=None),
            None)
        reports = self.assertReports(
            check,
            [self.mk_pkg("1", "x86 amd64"),
             self.mk_pkg("2"),
             self.mk_pkg("3")])
        assert len(reports) == 1
        assert reports[0].version == '3'