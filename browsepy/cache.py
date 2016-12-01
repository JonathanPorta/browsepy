

import functools
import threading


NOT_FOUND = object()


class HashTuple(tuple):
    '''
    Tuple object with cached __hash__ and __repr__.
    '''

    def __hash__(self):
        '''
        Self-caching hash method.

        x.__hash__() <==> hash(x)
        '''
        res = tuple.__hash__(self)
        self.__hash__ = lambda x: res
        return res

    def __repr__(self):
        '''
        Self-caching representation method.

        x.__repr__() <==> repr(x)
        '''
        res = (
            '<{0.__class__.__module__}.{0.__class__.__name__} {1} {2}>'
            ).format(self, hash(self), tuple(self))
        self.__repr__ = lambda x: res
        return res


class MemoizeManager(object):
    '''
    Cache manager object exposed via :attr:`cache` of memoized functions (see
    :meth:`BaseCache.memoize`).
    '''
    hashtuple_class = HashTuple
    NOT_CACHED = object()

    def __init__(self, cache):
        self._hits = 0
        self._misses = 0
        self._cache = cache

    @property
    def hits(self):
        '''
        :returns: number of times result was cached
        :rtype: integer
        '''
        return self._hits

    @property
    def misses(self):
        '''
        :returns: number of times result was not cached
        :rtype: integer
        '''
        return self._missses

    @classmethod
    def make_key(cls, args, kwargs, tuple=tuple):
        '''
        Make a cache key from optionally typed positional and keyword arguments

        The key is constructed in a way that is flat as possible rather than
        as a nested structure that would take more memory.

        If there is only a single argument and its data type is known to cache
        its hash value, then that argument is returned without a wrapper.  This
        saves space and improves lookup speed.
        '''
        key_args = tuple([(arg, arg.__class__) for arg in args])
        key_kwargs = tuple([
            (key, value, value.__class__)
            for key, value in sorted(kwargs.items())
            ])
        return cls.hashtuple_class((key_args, key_kwargs))

    def run(self, fnc, *args, **kwargs):
        key = self.make_key(args, kwargs)
        result = self._cache.get(key, self.NOT_CACHED)
        if result is not self.NOT_CACHED:
            self._hits += 1
            return result
        self._misses += 1
        self._cache[key] = result = fnc(*args, **kwargs)
        return result

    def pop(self, *args, **kwargs):
        key = self.make_key(args, kwargs)
        return self._cache.pop(key, None)

    def clear(self):
        '''
        Clear both cache and statistics.
        '''
        self._hits = 0
        self._misses = 0
        self._cache.clear()


class BaseCache(object):
    '''
    Abstract cache implementation.

    This class does not really store anything, this is let to implementations.
    '''
    memoize_class = MemoizeManager

    def __setitem__(self, key, value):
        pass

    def __getitem__(self, key):
        raise KeyError(key)

    def __delitem__(self, key):
        raise KeyError(key)

    def __contains__(self, key):
        return False

    def pop(self, key, default=NOT_FOUND):
        if default is NOT_FOUND:
            raise KeyError(key)
        return default

    def get(self, key, default=None):
        return default

    def clear(self):
        pass

    def memoize(self, fnc):
        '''
        Decorate given function and memoize its results using currente cache.

        :param fnc: function to decorate
        :type fnc: collections.abc.Callable
        :param maxsize: optional maximum size (defaults to 1024)
        :type maxsize: int
        :returns: wrapped cached function
        :rtype: function
        '''
        manager = self.memoize_class(self)

        @functools.wraps(fnc)
        def wrapped(*args, **kwargs):
            return manager.run(fnc, *args, **kwargs)
        wrapped.cache = manager
        return wrapped


class LRUCache(BaseCache):
    '''
    Cache object evicting least recently used objects (LRU) when maximum cache
    size is reached.

    It's way slower than python's :func:`functools.lru_cache` but provides an
    object-oriented implementation and manual cache eviction.
    '''
    lock_class = threading.RLock

    @property
    def full(self):
        '''
        :returns: True if size reached maxsize, False otherwise
        :rtype: bool
        '''
        return self._full

    @property
    def size(self):
        '''
        :returns: current size of result cache
        :rtype: int
        '''
        return len(self._cache)

    @property
    def maxsize(self):
        '''
        :returns: maximum size of result cache
        :rtype: int
        '''
        return self._maxsize

    def __init__(self, maxsize=1024):
        '''
        :param fnc:
        :type fnc: collections.abc.Callable
        :param maxsize: optional maximum cache size (defaults to 1024)
        :type maxsize: int
        '''
        self._cache = {}
        self._full = False
        self._maxsize = maxsize
        self._lock = self.lock_class()
        self._root = root = []
        root[:] = [root, root, None, None]

    def _bumpitem(self, key):
        PREV, NEXT = 0, 1
        root = self._root
        last = root[PREV]
        last[NEXT] = root[PREV] = link = self._cache[key]
        link[PREV] = last
        link[NEXT] = root

    def _getitem(self, key, default=NOT_FOUND):
        RESULT = 3
        link = self._cache.get(key)
        if link is not None:
            self._bumpitem(key)
            return link[RESULT]
        if default is NOT_FOUND:
            raise KeyError(key)
        return default

    def _setitem(self, key, value):
        PREV, NEXT, KEY, RESULT = 0, 1, 2, 3
        cache = self._cache
        root = self._root
        if key in cache:
            self._bumpitem(key)
            root[PREV][RESULT] = value
        elif self._full:
            # reuse old root
            oldroot = root
            oldroot[KEY] = key
            oldroot[RESULT] = value
            root = oldroot[NEXT]
            oldkey = root[KEY]
            root[KEY] = root[RESULT] = None
            del cache[oldkey]
            cache[key] = oldroot
            self._root = root
        else:
            last = root[PREV]
            link = [last, root, key, value]
            last[NEXT] = root[PREV] = cache[key] = link
            self._full = (len(cache) >= self._maxsize)
        return value

    def _popitem(self, key, default=NOT_FOUND):
        PREV, NEXT = 0, 1
        if default is NOT_FOUND:
            link_prev, link_next, key, result = self._cache.pop(key)
        else:
            link_prev, link_next, key, result = self._cache.pop(key, default)
        link_prev[NEXT] = link_next
        link_next[PREV] = link_prev
        return result

    def __getitem__(self, key):
        with self._lock:
            return self._getitem(key)

    def __setitem__(self, key, value):
        with self._lock:
            return self._setitem(key, value)

    def __delitem__(self, key):
        with self._lock:
            self._popitem(key)

    def __contains__(self, key):
        return key in self._cache

    def pop(self, key, default=NOT_FOUND):
        with self._lock:
            return self._popitem(key, default)

    def get(self, key, default=None):
        with self._lock:
            return self._getitem(key, default)

    def clear(self):
        with self._lock:
            self._cache.clear()
            self._root = root = []
            root[:] = [root, root, None, None]
            self._hits = 0
            self._misses = 0
            self._full = False
