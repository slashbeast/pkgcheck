# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


from pkgcore.test import TestCase

from pkgcore_checks import base


dummies = list('dummy-%s' % (i,) for i in xrange(0, 10))


class DummyTransform(object):

    """Dummy transform object just yielding its source with itself appended.

    Instances can be sensibly compared to each other, so comparing
    instances from the L{trans} helper function to instances in the
    predefined L{trans_up}, L{trans_down} and L{trans_everything}
    sequences works.
    """

    def __init__(self, source, target, cost=10):
        self.transforms = [(source, target, cost)]

    def transform(self, chunks):
        for chunk in chunks:
            yield chunk
        yield self

    def __repr__(self):
        return '%s(%s, %s, %s)' % ((
                self.__class__.__name__,) + self.transforms[0])

    def __eq__(self, other):
        return (self.__class__ is other.__class__ and
                self.transforms == other.transforms)

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        return 0


class DummySource(object):

    """Dummy source object just "producing" itself.

    You should use the instances in the L{sources} tuple instead of
    creating your own.
    """

    cost = 10

    def __init__(self, dummy):
        self.feed_type = dummy

    def feed(self):
        yield self

    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__, self.feed_type)


class DummySink(object):

    """Dummy sink object just yielding every fed to it with itself appended.

    You should use the instances in the L{sinks} tuple instead of
    creating your own.
    """

    def __init__(self, dummy):
        self.feed_type = dummy

    def feed(self, chunks, reporter):
        for chunk in chunks:
            yield chunk
        yield self

    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__, self.feed_type)


def trans(source, target, cost=10):
    return DummyTransform(dummies[source], dummies[target], cost)


sources = tuple(DummySource(dummy) for dummy in dummies)
trans_everything = tuple(DummyTransform(source, target)
                         for source in dummies for target in dummies)
trans_up = tuple(DummyTransform(dummies[i], dummies[i + 1])
                 for i in xrange(len(dummies) - 1))
trans_down = tuple(DummyTransform(dummies[i + 1], dummies[i], 1)
                   for i in xrange(len(dummies) - 1))
sinks = tuple(DummySink(dummy) for dummy in dummies)


class PlugTest(TestCase):

    def assertPipes(self, sinks, transforms, sources, *expected_pipes):
        """Check if the plug function yields the expected pipelines.

        The first three arguments are passed through to plug.
        Further arguments are the pipes that should be returned.
        They are interpreted as a set (since the return order from plug
        is unspecified).
        """
        expected_pipes = set(expected_pipes)
        actual_pipes = set(
            tuple(t) for t in base.plug(sinks, transforms, sources, None))
        good = expected_pipes & actual_pipes
        expected_pipes -= good
        actual_pipes -= good
        if expected_pipes or actual_pipes:
            # Failure. Rerun in debug mode (tuple to drive the generator).
            tuple(base.plug(sinks, transforms, sources, None, True))
            message = ['', '', 'Expected:']
            for pipe in expected_pipes:
                message.extend(str(p) for p in pipe)
            message.extend(['', 'Got:'])
            for pipe in actual_pipes:
                message.extend(str(p) for p in pipe)
            self.fail('\n'.join(message))

    def test_plug(self):
        self.assertPipes(
            [sinks[2]],
            trans_everything,
            [sources[0]],
            (sources[0], trans(0, 2), sinks[2]))
        self.assertPipes(
            [sinks[2]],
            trans_up,
            [sources[0]],
            (sources[0], trans(0, 1), trans(1, 2), sinks[2]))

    def test_no_transform(self):
        self.assertPipes(
            [sinks[0]],
            trans_everything,
            [sources[0]],
            (sources[0], sinks[0]))
        self.assertPipes(
            [sinks[0]],
            [],
            [sources[0]],
            (sources[0], sinks[0]))

    def test_too_many_sources(self):
        self.assertPipes(
            [sinks[3]],
            trans_everything,
            sources,
            (sources[3], sinks[3]))
        self.assertPipes(
            [sinks[2], sinks[4]],
            [trans(1, 2), trans(3, 4), trans(4, 5)],
            [sources[1], sources[3]],
            (sources[1], trans(1, 2), sinks[2]),
            (sources[3], trans(3, 4), sinks[4]))

    def test_grow(self):
        self.assertPipes(
            [sinks[1], sinks[0]],
            trans_up,
            [sources[0]],
            (sources[0], sinks[0], trans(0, 1), sinks[1]))
        self.assertPipes(
            [sinks[1], sinks[0]],
            trans_everything,
            [sources[0]],
            (sources[0], sinks[0], trans(0, 1), sinks[1]))
        self.assertPipes(
            [sinks[2], sinks[0]],
            trans_up,
            [sources[0]],
            (sources[0], sinks[0], trans(0, 1), trans(1, 2), sinks[2]))
        self.assertPipes(
            [sinks[2], sinks[1]],
            trans_up,
            [sources[0]],
            (sources[0], trans(0, 1), sinks[1], trans(1, 2), sinks[2]))
