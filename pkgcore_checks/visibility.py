# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from snakeoil.compatibility import any
from pkgcore_checks import base, addons
from snakeoil.iterables import caching_iter
from snakeoil.lists import stable_unique, iflatten_instance, iflatten_func
from pkgcore.ebuild.atom import atom
from snakeoil.demandload import demandload
from pkgcore.package.mutated import MutatedPkg
from itertools import imap
demandload(globals(), "snakeoil.xml:escape")


class FakeConfigurable(object):
    configurable = True
    use = ()
    __slots__ = ('_raw_pkg', '_profile')

    def __init__(self, pkg, profile):
        object.__setattr__(self, '_raw_pkg', pkg)
        object.__setattr__(self, '_profile', profile)

    def request_enable(self, attr, *vals):
        if attr != 'use':
            return False
        set_vals = frozenset(vals)
        if set_vals.difference(x.lstrip('-+') for x in self.iuse):
            # requested a flag that doesn't exist in iuse
            return False
        # if any of the flags are in masked_use, it's a no go.
        return not set_vals.issubset(self._profile.masked_use.
            pull_data(self._raw_pkg))

    def request_disable(self, attr, *vals):
        if attr != 'use':
            return False
        set_vals = frozenset(vals)
        if set_vals.difference(x.lstrip('-+') for x in self.iuse):
            # requested a flag that doesn't exist in iuse
            return False
        # if any of the flags are forced_use, it's a no go.
        return not set_vals.issubset(self._profile.forced_use.
            pull_data(self._raw_pkg))

    def rollback(self, point=0):
        return True

    def changes_count(self):
        return 0

    def __getattr__(self, attr):
        return getattr(self._raw_pkg, attr)

    def __setattr__(self, attr, val):
        raise AttributeError(self, 'is imutable')



if hasattr(atom, '_transitive_use_atom'):

    def _eapi2_flatten(val, atom_kls=atom,
        transitive_use_atom=atom._transitive_use_atom):
        return isinstance(val, atom_kls) and \
            not isinstance(val, transitive_use_atom)

    def visit_atoms(pkg, stream):
        if pkg.eapi < 2:
            return iflatten_instance(stream, atom)
        return iflatten_func(stream, _eapi2_flatten)
else:
    def visit_atoms(pkg, stream):
        return iflatten_instance(stream, atom)

if hasattr(atom, 'reduce_atom'):
    def strip_atom_use(inst):
        return inst.reduce_atom('use', invert=True)
else:
    def strip_atom_use(inst):
        if '=*' == inst.op:
            s = '=%s*' % inst.cpvstr
        else:
            s = inst.op + inst.cpvstr
        if inst.blocks:
            s = '!' + s
            if not inst.blocks_temp_ignorable:
                s = '!' + s
        if inst.slot:
            s += ':%s' % ','.join(inst.slot)
        return atom(s)


class VisibleVcsPkg(base.Result):
    """pkg is vcs based, but visible"""

    __slots__ = ("category", "package", "version", "profile", "arch")

    threshold = base.versioned_feed

    def __init__(self, pkg, arch, profile):
        base.Result.__init__(self)
        self._store_cpv(pkg)
        self.arch = arch.lstrip("~")
        self.profile = profile

    @property
    def short_desc(self):
        return "VCS version visible for arch %s, profile %s" % (
            self.arch, self.profile)


class NonExistantDeps(base.Result):
    """No matches exist for a depset element"""

    __slots__ = ("category", "package", "version", "attr", "atoms")

    threshold = base.versioned_feed

    def __init__(self, pkg, attr, nonexistant_atoms):
        base.Result.__init__(self)
        self._store_cpv(pkg)
        self.attr = attr
        self.atoms = tuple(str(x) for x in nonexistant_atoms)

    @property
    def short_desc(self):
        return "depset %s: nonexistant atoms [ %s ]" % (
            self.attr, ', '.join(self.atoms))


class NonsolvableDeps(base.Result):
    """No potential solution for a depset attribute"""

    __slots__ = ("category", "package", "version", "attr", "profile",
        "keyword", "potentials")

    threshold = base.versioned_feed

    def __init__(self, pkg, attr, keyword, profile, horked):
        base.Result.__init__(self)
        self._store_cpv(pkg)
        self.attr = attr
        self.profile = profile
        self.keyword = keyword
        self.potentials = tuple(str(x) for x in stable_unique(horked))

    @property
    def short_desc(self):
        return "nonsolvable depset(%s) keyword(%s) profile (%s): " \
            "solutions: [ %s ]" % (self.attr, self.keyword, self.profile,
            ', '.join(self.potentials))


class VisibilityReport(base.Template):

    """Visibility dependency scans.
    Check that at least one solution is possible for a pkg, checking all
    profiles (defined by arch.list) visibility modifiers per stable/unstable
    keyword
    """

    feed_type = base.versioned_feed
    required_addons = (
        addons.ArchesAddon, addons.QueryCacheAddon, addons.ProfileAddon,
        addons.EvaluateDepSetAddon)
    known_results = (VisibleVcsPkg, NonExistantDeps, NonsolvableDeps)

    vcs_eclasses = frozenset(["subversion", "git", "cvs", "darcs"])

    def __init__(self, options, arches, query_cache, profiles, depset_cache):
        base.Template.__init__(self, options)
        self.query_cache = query_cache.query_cache
        self.depset_cache = depset_cache
        self.profiles = profiles
        self.arches = frozenset(x.lstrip("~") for x in options.arches)

    def feed(self, pkg, reporter):
        # query_cache gets caching_iter partial repo searches shoved into it-
        # reason is simple, it's likely that versions of this pkg probably
        # use similar deps- so we're forcing those packages that were
        # accessed for atom matching to remain in memory.
        # end result is less going to disk

        fvcs = self.vcs_eclasses
        for eclass in pkg.data.get("_eclasses_", ()):
            if eclass in fvcs:
                # vcs ebuild that better not be visible
                self.check_visibility_vcs(pkg, reporter)
                break

        for attr, depset in (("depends", pkg.depends),
            ("rdepends", pkg.rdepends), ("post_rdepends", pkg.post_rdepends)):
            nonexistant = set()
            for orig_node in visit_atoms(pkg, depset):

                node = strip_atom_use(orig_node)
                h = str(node)
                if h not in self.query_cache:
                    if h in self.profiles.global_insoluable:
                        nonexistant.add(node)
                        # insert an empty tuple, so that tight loops further
                        # on don't have to use the slower get method
                        self.query_cache[h] = ()

                    else:
                        matches = caching_iter(
                            self.options.search_repo.itermatch(node))
                        if matches:
                            self.query_cache[h] = matches
                            if orig_node is not node:
                                self.query_cache[str(orig_node)] = matches
                        elif not node.blocks and not node.category == "virtual":
                            nonexistant.add(node)
                            self.query_cache[h] = ()
                            self.profiles.global_insoluable.add(h)
                elif not self.query_cache[h]:
                    nonexistant.add(node)

            if nonexistant:
                reporter.add_report(NonExistantDeps(pkg, attr, nonexistant))

        del nonexistant

        for attr, depset in (("depends", pkg.depends),
            ("rdepends", pkg.rdepends), ("post_rdepends", pkg.post_rdepends)):

            for edepset, profiles in self.depset_cache.collapse_evaluate_depset(
                pkg, attr, depset):

                self.process_depset(pkg, attr, edepset, profiles, reporter)

    def check_visibility_vcs(self, pkg, reporter):
        for key, profiles in self.profiles.profile_filters.iteritems():
            if key.startswith("~") or key.startswith("-"):
                continue
            for profile in profiles:
                if profile.visible(pkg):
                    reporter.add_report(VisibleVcsPkg(pkg,
                        profile.key, profile.name))

    def process_depset(self, pkg, attr, depset, profiles, reporter):
        csolutions = depset.cnf_solutions()

        for profile in profiles:
            failures = set()
            # is it visible?  ie, is it masked?
            # if so, skip it.
            # long term, probably should do testing in the same respect we do
            # for other visibility tiers
            cache = profile.cache
            provided = profile.provides_repo.match
            is_virtual = profile.virtuals.match
            insoluable = profile.insoluable
            visible = profile.visible
            for required in csolutions:
                if any(True for a in required if a.blocks):
                    continue
                for node in required:
                    h = str(node)

                    if h in insoluable:
                        pass
                    elif h in cache:
                        break
                    elif provided(node):
                        break
                    elif is_virtual(node):
                        cache.add(h)
                        break
                    elif node.category == "virtual" and h not in self.query_cache:
                        insoluable.add(h)
                    else:
                        src = self.query_cache[str(strip_atom_use(node))]
                        if node.use:
                            src = (pkg for pkg in src if node.force_True(
                                FakeConfigurable(pkg, profile)))
                        if any(True for pkg in src if
                            visible(pkg)):
                            cache.add(h)
                            break
                        else:
                            insoluable.add(h)
                else:
                    # no matches.  not great, should collect them all
                    failures.update(required)
            if failures:
                reporter.add_report(NonsolvableDeps(pkg, attr, profile.key,
                    profile.name, list(failures)))
