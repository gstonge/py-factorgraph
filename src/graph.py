'''
Implementation of factor graph.

Author: mbforbes

Current approach (order matters):
-   (1) add RVs
-   (2) add factors to connect them
-   (3) set potentials on factors
-   (4) run inference
-   (5) compute marginals

For some things below, we'll want to represent what's going on in mathematical
notation. Let's define some variables that we'll use throughout to help:

RV vars:
    X       the set of n random variables
    X_i     random variable i (1 <= i <= n)
    v_i     number of values that X_i can take (nonstandard but I wanted one)
    x_ij    a particular value for X_i (1 <= j <= v_i)
    x_i     a simpler (lazy) notation for x_ij (which j doesn't matter)
    x       a set of x_i for i = 1..n (imagine x_1j, x_2k, ..., x_nz)

Factor vars:
    F       the set of m factors
    f_a     factor a (1 <= a <= m) connecting a subset of X
    X_a     the subset of X (RVs) that f_a connects
    x_a     the subset of x (values for RVs) that f_a connects

Functions:
    p(x)    joint distribution for p(X = x)

Notes:
    f_a(x) = f_a(x_a)   Because f_a only touches (is only a function of) x_a,
                        it will "ignore" the other x_i in x that aren't in x_a.
                        Thus, we write f_a(x_a) for convenience to show exactly
                        what f_a operates on.
'''

# Imports
# -----------------------------------------------------------------------------

# Builtins
import code  # code.interact(local=dict(globals(), **locals()))

# 3rd party
import numpy as np


# Constants
# -----------------------------------------------------------------------------

# Settings

# Use this to turn all debugging on or off. Intended use: keep on when you're
# trying stuff out. Once you know stuff works, turn off for speed. Can also
# specify when creating each instance, but this global switch is provided for
# convenience.
DEBUG_DEFAULT = True

# This is the maximum number of iterations that we let loopy belief propagation
# run before cutting it off.
LBP_MAX_ITERS = 50


# Classes
# -----------------------------------------------------------------------------

class Graph(object):
    '''
    Graph right now has no point, really (except bookkeeping all the RVs and
    factors, assuming we remember to add them), so this might be removed or
    functionality might be stuffed in here later.

    NOTE: All RVs must have unique names.

    TODO: Consider making Node base class which RV and Factor extend.

    TODO: Consider making better methods for creating and adding RVs and
    Factors all at once. Really shouldn't even need a graph object, but if
    we're going to have one (it's kind of nice conceptually), it should have a
    nicer interface.
    '''

    def __init__(self, debug=DEBUG_DEFAULT):
        # add now
        self.debug = debug

        # added later
        self._rvs = {}
        # TODO: Consider making dict for speed.
        self._factors = []

    def add_rv(self, rv):
        '''
        Node (RV|Factor)
        '''
        # Check RV with same name not already added.
        if self.debug:
            assert rv.name not in self._rvs
        # Add it.
        self._rvs[rv.name] = rv

    def add_factor(self, factor):
        if self.debug:
            # Check the same factor hasn't already been added.
            assert factor not in self._factors

            # Check factor connecting to exactly the same set of nodes doesn't
            # already exist. This isn't mandated by factor graphs by any means,
            # but it's a heuristic to prevent bugs; if you're adding factors
            # that connect the same set of ndoes, you're either doing something
            # weird (and can probably reformulate your graph structure to avoid
            # this duplication), or you have a bug.
            factor_rvs = sorted(factor._rvs)
            for f in self._factors:
                rvs = sorted(f._rvs)
                assert factor_rvs != rvs
        # Add it.
        self._factors += [factor]

    def joint(self, x):
        '''
        Joint is over the factors.

        For a probability, we use the normalization constant 1/Z

            p(x) = 1/Z \product_a^{1..m} f_a(x_a)

        If we don't care what the normalization is, we just write this without
        1/Z:

            p(x) = \product_a^{1..m} f_a(x_a)

        This is currently implemented without normalization. I might want to
        add it in the future. I don't know yet.

        Args:
            x ({str: str|int}) map of node names to assignments. The
                assignments can be labels or indexes
        '''
        # ensure the assignment x given is valid
        if self.debug:
            # check the length (that assignments to all RVs are provided)
            assert len(x) == len(self._rvs)

            # check that each assignment is valid (->)
            for name, label in x.iteritems():
                assert name in self._rvs
                assert self._rvs[name].has_label(label)

            # check that each RV has a valid assignment (<-)
            for name, rv in self._rvs.iteritems():
                assert name in x
                assert rv.has_label(x[name])

        # Do the actual computation.
        # NOTE: This could be sped up as all factors can be computed in
        # parallel.
        prod = 1.0
        for f in self._factors:
            prod *= f.eval(x)
        return prod

    def bf_best_joint(self):
        '''
        Brute-force algorithm to compute the best joint assignment to the
        factor graph given the current potentials in the factors.

        This takes O(v^n) time, where
            v   is the # of possible assignments to each RV
            n   is the # of RVs

        This is bad. This function is given for debugging / proof of concept
        only.

        Returns:
            ({str: int}, float)
        '''
        return self._bf_bj_recurse({}, self._rvs.values())

    def _bf_bj_recurse(self, assigned, todo):
        '''
        Helper method for bf_best_joint.

        Args:
            assigned ({str: int})
            todo ([RV])
        '''
        # base case: just look up the current assignment
        if len(todo) == 0:
            return assigned, self.joint(assigned)

        # recursive case: pull off one RV and try all options.
        best_a, best_r = None, 0.0
        rv = todo[0]
        todo = todo[1:]
        for val in range(rv.n_opts):
            new_a = assigned.copy()
            new_a[rv.name] = val
            full_a, r = self._bf_bj_recurse(new_a, todo)
            if r > best_r:
                best_r = r
                best_a = full_a
        return best_a, best_r

    def lbp(self, normalize=False, max_iters=LBP_MAX_ITERS):
        '''
        Loopy belief propagation.

        FAQ:

        -   Q: Do we have do updates in some specific order?
            A: No.

        -   Q: Can we intermix computing messages for Factor and RV nodes?
            A: Yes.

        -   Q: Do we have to make sure we only send messages on an edge once
               messages from all other edges are received?
            A: No. By sorting the nodes, we can kind of approximate this. But
               this constraint is only something that matters if you want to
               converge in 1 iteration on an acyclic graph.

        -   Q: Do factors' potential functions change during (L)BP?
            A: No. Only the messages change.
        '''
        # Sketch of algorithm:
        # -------------------
        # preprocessing:
        # - sort nodes by number of edges
        #
        # note:
        # - every time message sent, normalize if too large or small
        #
        # Algo:
        # - initialize messages to 1
        # - until convergence or max iters reached:
        #     - for each node in sorted list (fewest edges to most):
        #         - compute outgoing messages to neighbors
        #         - check convergence of messages
        nodes = self._sorted_nodes()
        self._init_messages(nodes)

        cur_iter, converged = 0, False
        while cur_iter < max_iters and not converged:
            # Bookkeeping
            cur_iter += 1

            # debug
            # self.print_messages(nodes)
            # print 'lbp iter:', cur_iter

            # Comptue outgoing messages:
            converged = True
            for n in nodes:
                n_converged = n.recompute_outgoing(normalize=normalize)
                converged = converged and n_converged

        return cur_iter, converged

    def _sorted_nodes(self):
        '''
        Returns
            [RV|Factor] sorted by # edges
        '''
        rvs = self._rvs.values()
        facs = self._factors
        nodes = rvs + facs
        return sorted(nodes, key=lambda x: x.n_edges())

    def _init_messages(self, nodes):
        '''
        Sets all messages to uniform.

        Args:
            nodes ([RV|Factor])
        '''
        for n in nodes:
            n.init_lbp()

    def print_sorted_nodes(self):
        print self._sorted_nodes()

    def print_messages(self, nodes=None):
        '''
        Prints (outgoing) messages for node in nodes.

        Args:
            nodes ([RV|Factor])
        '''
        if nodes is None:
            nodes = self._sorted_nodes()
        print 'Current outgoing messages:'
        for n in nodes:
            n.print_messages()

    def print_rv_marginals(self, normalize=False):
        '''
        Displays marginals for all RVs.

        The marginal for RV i is computed as:

            marg = prod_{neighboring f_j} message_{f_j -> i}

        Args:
            normalize (bool, opt) whether to turn this into a probability
                distribution
        '''
        # Preamble
        disp = 'Marginals for RVs'
        if normalize:
            disp += ' (normalized)'
        disp += ':'
        print disp

        for name, rv in self._rvs.iteritems():
            # Compute marginal
            marg, _ = rv.get_belief()
            if normalize:
                marg /= sum(marg)

            # Dispaly
            print name
            vals = range(rv.n_opts)
            if len(rv.labels) > 0:
                vals = rv.labels
            for i in range(len(vals)):
                print '\t', vals[i], '\t', marg[i]

    def print_stats(self):
        print 'Graph stats:'
        print '\t%d RVs' % (len(self._rvs))
        print '\t%d factors' % (len(self._factors))


class RV(object):
    '''
    NOTE: All RVs must have unique names.
    '''

    def __init__(self, name, n_opts, labels=[], debug=DEBUG_DEFAULT):
        '''
        name (str)                must be globally unique w.r.t. other RVs
        n_opts (int)              how many values it can take
        labels ([str], opt)       opt names for each var. len must == n_opts
        debug (bool, opt)         a gazillion asserts
        '''
        # validation
        if debug:
            # labels must be [str] if provided
            for l in labels:
                assert type(l) is str

            # must have n_opts labels if provided
            assert len(labels) == 0 or len(labels) == n_opts

        # vars set at construction time
        self.name = name
        self.n_opts = n_opts
        self.labels = labels
        self.debug = debug

        # vars added later
        # TODO: consider making dict for speed.
        self._factors = []
        self._outgoing = None

    def __repr__(self):
        return self.name

    def __hash__(self):
        return hash(self.name)

    def init_lbp(self):
        '''
        Clears any existing messages and inits all messages to uniform.
        '''
        self._outgoing = [np.ones(self.n_opts) for f in self._factors]

    def print_messages(self):
        '''
        Displays the current outgoing messages for this RV.
        '''
        for i, f in enumerate(self._factors):
            print '\t', self, '->', f, '\t', self._outgoing[i]

    def recompute_outgoing(self, normalize=False):
        '''
        TODO: Consider returning SSE for convergence checking.

        TODO: Is normalizing each outgoing message at the very end the right
              thing to do?

        Returns:
            bool whether this RV converged
        '''
        # Good old safety.
        if self.debug:
            assert self._outgoing is not None, 'must call init_lbp() first'

        # Save old for convergence check.
        old_outgoing = self._outgoing[:]

        # Get all incoming messages.
        total, incoming = self.get_belief()

        # Compute all outgoing messages and return whether convergence
        # happened.
        convg = True
        for i in range(len(self._factors)):
            o = total/incoming[i]
            if normalize:
                o /= sum(o)
            self._outgoing[i] = o
            convg = convg and \
                sum(np.isclose(old_outgoing[i], self._outgoing[i])) == \
                self.n_opts
        return convg

    def get_outgoing_for(self, f):
        '''
        Gets outgoing message for factor f.

        Args:
            f (Factor)

        Returns:
            np.ndarray of length self.n_opts
        '''
        # Good old safety.
        if self.debug:
            assert self._outgoing is not None, 'must call init_lbp() first'

        for i, fac in enumerate(self._factors):
            if f == fac:
                return self._outgoing[i]

    def get_belief(self):
        '''
        Returns the belief (AKA marginal probability) of this RV, using its
        current incoming messages.

        Returns tuple(
            marginal (np.ndarray)   of length self.n_opts         ,
            incoming ([np.ndarray]) message for f in self._factors,
        )
        '''
        incoming = []
        total = np.ones(self.n_opts)
        for i, f in enumerate(self._factors):
            m = f.get_outgoing_for(self)
            if self.debug:
                assert m.shape == (self.n_opts,)
            incoming += [m]
            total *= m
        return (total, incoming)

    def n_edges(self):
        '''
        Returns:
            int how many factors this RV is connected to
        '''
        return len(self._factors)

    def has_label(self, label):
        '''
        Returns whether label indicates a valid value for this RV.

        Args:
            label (int|str)

        returns
            bool
        '''
        # If int, make sure fits in n_opts. If str, make sure it's in the list.
        if len(self.labels) == 0:
            # Tracking ints only. Provided label must be int.
            if self.debug:
                assert type(label) is int
            return label < self.n_opts
        else:
            # Tracking strs only. Provided label can be int or str.
            if self.debug:
                assert type(label) is int or type(label) is str
            if type(label) is str:
                return label in self.labels
            # Default: int
            return label < self.n_opts

    def get_int_label(self, label):
        '''
        Returns the integer-valued label for this label. The provided label
        might be an integer (in which case it's already in the correct form and
        will be returned unchanged) or a string (in which case it will be
        turned into an int).

        This assumes the caller has already ensured this is a valid label with
        has_label.

        Args:
            label (int|str)

        returns
            int
        '''
        if type(label) is int:
            return label
        # assume string otherwise
        return self.labels.index(label)

    def attach(self, factor):
        '''
        Don't call this; automatically called by Factor's attach(...). This
        doesn't update the factor's attachment (which is why you shouldn't call
        it).

        factor (Factor)
        '''
        # check whether factor already added to rv; reach factor should be
        # added at most once to an rv.
        if self.debug:
            for f in self._factors:
                # We really only need to worry about the exact instance here,
                # so just using the builtin object (mem address) equals.
                assert f != factor, ('Can\'t re-add factor %r to rv %r' %
                                     (factor, self))

        # Do the registration
        self._factors += [factor]


class Factor(object):
    '''
    Invariant: RVs (self._rvs), dims of potential (self._potential), and outgoing
    messages (self._outgoing) must refer to the same RVs in identical order.
    '''

    def __init__(self, rvs, name='', debug=DEBUG_DEFAULT):
        '''
        rvs ([RV])
        name (str, opt)
        debug (bool, opt)
        '''
        # at construction time
        self.name = name
        self.debug = debug

        # add later using methods
        # TODO: consider making dict for speed.
        self._rvs = []
        self._potential = None
        self._outgoing = None

        # set the rvs now
        for rv in rvs:
            self.attach(rv)

    def __repr__(self):
        return 'f(' + ', '.join([str(rv) for rv in self._rvs]) + ')'

    def n_edges(self):
        '''
        Returns:
            int how many RVs this Factor is connected to
        '''
        return len(self._rvs)

    def init_lbp(self):
        '''
        Clears any existing messages and inits all messages to uniform.
        '''
        self._outgoing = [np.ones(r.n_opts) for r in self._rvs]

    def get_outgoing_for(self, rv):
        '''
        Gets the message for the random variable rv that this factor is
        connected to. Prereq: this must be connected to rv. Duh. This code
        doesn't check that.

        Args:
            rv (RV)

        Returns:
            np.ndarray of length rv.n_opts
        '''
        # Good old safety.
        if self.debug:
            assert self._outgoing is not None, 'must call init_lbp() first'

        for i, r in enumerate(self._rvs):
            if r == rv:
                return self._outgoing[i]

    def recompute_outgoing(self, normalize=False):
        '''
        TODO: Consider returning SSE for convergence checking.

        Returns:
            bool whether this Factor converged
        '''
        # Good old safety.
        if self.debug:
            assert self._outgoing is not None, 'must call init_lbp() first'

        # Save old for convergence check.
        old_outgoing = self._outgoing[:]

        # (Product:) Multiply RV messages into "belief".
        incoming = []
        belief = self._potential.copy()
        for i, rv in enumerate(self._rvs):
            m = rv.get_outgoing_for(self)
            if self.debug:
                assert m.shape == (rv.n_opts,)
            # Reshape into the corect axis (for combining). For example, if our
            # incoming message (And thus rv.n_opts) has length 3, our belief
            # has 5 dimensions, and this is the 2nd (of 5) dimension(s), then
            # we want the shape of our message to be (1, 3, 1, 1, 1), which
            # means we'll use [1, -1, 1, 1, 1] to project our (3,1) array into
            # the correct dimension.
            #
            # Thanks to stackoverflow:
            # https://stackoverflow.com/questions/30031828/multiply-numpy-
            #     ndarray-with-1d-array-along-a-given-axis
            proj = np.ones(len(belief.shape), int)
            proj[i] = -1
            m_proj = m.reshape(proj)
            incoming += [m_proj]
            # Combine to save as we go
            belief *= m_proj

        # Divide out individual belief and (Sum:) add for marginal.
        convg = True
        all_idx = range(len(belief.shape))
        for i, rv in enumerate(self._rvs):
            rv_belief = belief / incoming[i]
            axes = tuple(all_idx[:i] + all_idx[i+1:])
            o = rv_belief.sum(axis=axes)
            if self.debug:
                assert self._outgoing[i].shape == (rv.n_opts, )
            if normalize:
                o /= sum(o)
            self._outgoing[i] = o
            convg = convg and \
                sum(np.isclose(old_outgoing[i], self._outgoing[i])) == \
                rv.n_opts

        return convg

    def print_messages(self):
        '''
        Displays the current outgoing messages for this Factor.
        '''
        for i, rv in enumerate(self._rvs):
            print '\t', self, '->', rv, '\t', self._outgoing[i]

    def attach(self, rv):
        '''
        Call this to attach this factor to the RV rv. Clears any potential that
        has been set.

        rv (RV)
        '''
        # check whether rv already added to factor; reach rv should be added at
        # most once to a factor.
        if self.debug:
            for r in self._rvs:
                # We really only need to worry about the exact instance here,
                # so just using the builtin object (mem address) equals.
                assert r != rv, 'Can\'t re-add RV %r to factor %r' % (rv, self)

        # register with rv
        rv.attach(self)

        # register rv here
        self._rvs += [rv]

        # Clear potential as dimensions no longer match.
        self._potential = None

    def set_potential(self, b):
        '''
        Call this to set the potential for a factor. The passed potential b
        must dimensionally match all attached RVs.

        The dimensions can be a bit confusing. They iterate through the
        dimensions of the RVs in order.

        For example, say we have three RVs, which can each take on the
        following values:

            A {a, b, c}
            B {d, e}
            C {f, g}

        Now, say we have a facor which connects all of them (i.e. f(A,B,C)).
        The dimensions of the potential for this factor are 3 x 2 x 2. You can
        imagine a 3d table of numbers:

                        a b c
            a b c     +------
          + -----   d | g g g
        d | f f f / e | g g g
        e | f f f /

        This looks like you have two "sheets" of numbers. The lower sheet (on
        the left) contains the values for C = f, and the upper sheet (on the
        right) contains the values for C = g. A single cell contains the joint.
        For example, the top-left cell of the bottom sheet contains the value
        for f(A=a, B=d, C=f), and the middle-bottom cell of the top sheet
        contains the value for f(A=b, B=e, c=g).

        The confusing thing (for me) is that a single potential of shape (3, 2,
        2) is represented in numpy as the following array:

           [[[n, n],
             [n, n]],

            [[n, n],
             [n, n]],

            [[n, n],
             [n, n]]]

        Though this still has twelve numbers, it wasn't how I was
        conceptualizing it. What gives? Well, what we're doing is indexing in
        the correct order. So, the first dimension, 3, indexes the value for
        the variable A. This visually splits our table into three areas, one
        each for A=a, A=b, and A=c. For each area, we have a 2 x 2 table. These
        would be represented in our 3d diagram above by three vertial sheets.
        Each 2 x 2 table has the values for B and C.

        So it really turns out I'd drawn my first table wrong for thinking
        about numpy arrays. You want to draw them by splitting up tables by the
        earlier Rvs. This would look like:

        A = a:
                d e
              +----
            d | n n
            e | n n

        A = b:
                f g
              +----
            d | n n
            e | n n

        A = c:
                f g
              +----
            d | n n
            e | n n

        Args:
            b (np.array)
        '''
        # check that the new potential has the correct shape
        if self.debug:
            # ensure overall dims match
            got = len(b.shape)
            want = len(self._rvs)
            assert got == want, ('potential %r has %d dims but needs %d' %
                                 (b, got, want))

            # Ensure each dim matches.
            for i, d in enumerate(b.shape):
                got = d
                want = self._rvs[i].n_opts
                assert got == want, (
                    'potential %r dim #%d has %d opts but rv has %d opts' %
                    (b, i+1, got, want))

        # Set it
        self._potential = b

    def eval(self, x):
        '''
        Returns a single cell of the potential function.

        Call this factor f_a. This returns f_a's potential function value for a
        full assignment to X_a, which we call x_a.

        Note that we accept x passed in, which is a full assignment to x. This
        accepts either x (full assignment) or x_a (assignment that this factor
        needs). This function only uses x_a [subset of] x.

        This checks (if debug is on) that all attached RVs have a valid
        assignment in x. Note that if this is begin called from Graph.joint(),
        this property is also checked there.
        '''
        if self.debug:
            # check that each RV has a valid assignment (<-)
            for rv in self._rvs:
                assert rv.name in x
                assert rv.has_label(x[rv.name])

        # slim down potential into desired value.
        ret = self._potential
        for r in self._rvs:
            ret = ret[r.get_int_label(x[r.name])]

        # should return a single number
        if self.debug:
            assert type(ret) is not np.ndarray

        return ret


# TODO(mbforbes): Remove all the main stuff once you have tests for this.

def pyfac_toygraph_test():
    '''
    ToyGraph test from pyfac
    (https://github.com/rdlester/pyfac/blob/master/graphTests.py).
    '''

    # rvs
    a = RV('a', 3)
    b = RV('b', 2)

    # facs
    f_b = Factor([b])
    f_b.set_potential(np.array([0.3, 0.7]))
    f_ab = Factor([a, b])
    f_ab.set_potential(np.array([[0.2, 0.8], [0.4, 0.6], [0.1, 0.9]]))

    # make graph
    g = Graph()
    g.add_rv(a)
    g.add_rv(b)
    g.add_factor(f_b)
    g.add_factor(f_ab)

    # print stuff
    g.print_stats()
    print 'Best joint:', g.bf_best_joint()

    # (l)bp!
    g.print_sorted_nodes()
    iters, converged = g.lbp(normalize=True)
    print '(L)BP ran for %d iterations; converged = %r' % (iters, converged)
    g.print_messages()
    g.print_rv_marginals(normalize=True)

def pyfac_testgraph_test():
    '''
    TestGraph test from pyfac
    (https://github.com/rdlester/pyfac/blob/master/graphTests.py).
    '''
    # TODO: This.
    pass

def playing():
    # rvs
    r1 = RV('foo', 2)
    r2 = RV('bar', 3)

    # factors
    f = Factor([r1, r2])
    f_bar = Factor([r2])

    # potentials
    b = np.array([[3, 2, 0.32453563], [2, 5, 5]])
    f.set_potential(b)
    b2 = np.array([8.0, 2.0, 3.0])
    f_bar.set_potential(b2)

    # add to a graph
    g = Graph()
    g.add_rv(r1)
    g.add_rv(r2)
    g.add_factor(f)
    g.add_factor(f_bar)

    # Print stuff
    g.print_stats()
    print 'Joint for foo=2, bar=1:', g.joint({'foo': 1, 'bar': 1})
    print 'Best joint:', g.bf_best_joint()


def main():
    # playing()
    pyfac_toygraph_test()
    pyfac_testgraph_test()


if __name__ == '__main__':
    main()
