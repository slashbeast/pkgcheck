from pkgcore.ebuild.atom import atom
from pkgcore.ebuild.cpv import versioned_CPV
from pkgcore.ebuild.eapi import get_eapi
from pkgcore.ebuild.ebuild_src import package
from pkgcore.ebuild.misc import ChunkedDataDict, chunked_data
from pkgcore.package.metadata import factory
from pkgcore.repository.util import SimpleTree
from snakeoil.mappings import ImmutableDict
from snakeoil.osutils import pjoin
from snakeoil.sequences import split_negations
from snakeoil.test import TestCase

from pkgcheck import base


class FakePkg(package):
    def __init__(self, cpvstr, data=None, shared=None, parent=None):
        if data is None:
            data = {}

        for x in ("DEPEND", "RDEPEND", "PDEPEND", "IUSE", "LICENSE"):
            data.setdefault(x, "")

        cpv = versioned_CPV(cpvstr)
        package.__init__(self, shared, parent, cpv.category, cpv.package, cpv.fullver)
        package.local_use = ImmutableDict()
        object.__setattr__(self, "data", data)

    @property
    def eapi(self):
        return get_eapi(self.data.get('EAPI', '0'))


class FakeTimedPkg(package):

    __slots__ = "_mtime_"

    def __init__(self, cpvstr, mtime, data=None, shared=None, repo=None):
        if data is None:
            data = {}
        cpv = versioned_CPV(cpvstr)
        package.__init__(self, shared, factory(repo), cpv.category, cpv.package, cpv.fullver)
        object.__setattr__(self, "data", data)
        object.__setattr__(self, "_mtime_", mtime)


class FakeFilesDirPkg(package):

    __slots__ = ("path",)

    def __init__(self, cpvstr, repo, data=None, shared=None):
        if data is None:
            data = {}
        cpv = versioned_CPV(cpvstr)
        package.__init__(self, shared, factory(repo), cpv.category, cpv.package, cpv.fullver)
        object.__setattr__(self, "data", data)
        object.__setattr__(self, "path", pjoin(
            repo.location, cpv.category, cpv.package, f'{cpv.package}-{cpv.fullver}.ebuild'))


default_threshold_attrs = {
    base.repository_feed: (),
    base.category_feed: ('category',),
    base.package_feed: ('category', 'package'),
    base.versioned_feed: ('category', 'package', 'version'),
}
default_threshold_attrs[base.ebuild_feed] = default_threshold_attrs[base.versioned_feed]


class ReportTestCase(TestCase):

    _threshold_attrs = default_threshold_attrs.copy()

    def assert_known_results(self, *reports):
        for report in reports:
            self.assertIn(report.__class__, self.check_kls.known_results)

    def assertNoReport(self, check, data, msg=""):
        l = []
        if msg:
            msg = f"{msg}: "
        r = fake_reporter(lambda r: l.append(r))
        check.feed(data, r)
        self.assert_known_results(*l)
        self.assertEqual(
            l, [], msg="%s%s" %
            (msg, list(report.short_desc for report in l)))

    def assertReportSanity(self, *reports):
        for report in reports:
            attrs = self._threshold_attrs.get(report.threshold)
            self.assertTrue(attrs, msg=f"unknown threshold on {report.__class__!r}")
            for x in attrs:
                self.assertTrue(
                    hasattr(report, x),
                    msg=f"threshold {report.threshold}, missing attr {x}: " \
                        f"{report.__class__!r} {report}"
                    )

    def assertReports(self, check, data):
        l = []
        r = fake_reporter(lambda r: l.append(r))
        check.feed(data, r)
        self.assert_known_results(*l)
        self.assertTrue(
            l, msg="must get a report from %r %r, got none" %
            (check, data))
        self.assertReportSanity(*l)
        return l

    def assertIsInstance(self, obj, kls):
        self.assertTrue(isinstance(obj, kls), msg=f"{obj!r} must be {kls!r}")
        return obj

    def assertReport(self, check, data):
        r = self.assertReports(check, data)
        self.assert_known_results(*r)
        self.assertEqual(
            len(r), 1, msg="expected one report, got %i: %r" %
            (len(r), r))
        self.assertReportSanity(r[0])
        return r[0]


class fake_reporter(object):
    def __init__(self, callback):
        self.add_report = callback


class Options(dict):
    __setattr__ = dict.__setitem__
    __getattr__ = dict.__getitem__
    __delattr__ = dict.__delitem__


class FakeProfile(object):

    def __init__(self, masked_use={}, stable_masked_use={}, forced_use={},
                 stable_forced_use={}, pkg_use={}, provides={}, iuse_effective=[],
                 use=[], masks=[], unmasks=[], arch='x86', name='none'):
        self.provides_repo = SimpleTree(provides)

        self.masked_use = ChunkedDataDict()
        self.masked_use.update_from_stream(
            chunked_data(atom(k), *split_negations(v))
            for k, v in masked_use.items())
        self.masked_use.freeze()

        self.stable_masked_use = ChunkedDataDict()
        self.stable_masked_use.update_from_stream(
            chunked_data(atom(k), *split_negations(v))
            for k, v in stable_masked_use.items())
        self.stable_masked_use.freeze()

        self.forced_use = ChunkedDataDict()
        self.forced_use.update_from_stream(
            chunked_data(atom(k), *split_negations(v))
            for k, v in forced_use.items())
        self.forced_use.freeze()

        self.stable_forced_use = ChunkedDataDict()
        self.stable_forced_use.update_from_stream(
            chunked_data(atom(k), *split_negations(v))
            for k, v in stable_forced_use.items())
        self.stable_forced_use.freeze()

        self.pkg_use = ChunkedDataDict()
        self.pkg_use.update_from_stream(
            chunked_data(atom(k), *split_negations(v))
            for k, v in pkg_use.items())
        self.pkg_use.freeze()

        self.masks = tuple(map(atom, masks))
        self.unmasks = tuple(map(atom, unmasks))
        self.iuse_effective = set(iuse_effective)
        self.use = set(use)
        self.key = arch
        self.name = name
