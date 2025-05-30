import os, pickle, threading

class PickleCacheManager:
	_cache = {}
	_locks = {}

	@classmethod
	def get_cache(cls, filename, default={}):
		if filename not in cls._cache:
			cls._locks[filename] = threading.Lock();
			if os.path.exists(filename):
				with open(filename, "rb") as f:
					cls._cache[filename] = pickle.load(f);
			else:
				cls._cache[filename] = default;
		return cls._cache[filename];

	@classmethod
	def sync_cache(cls, filename):
		if filename not in cls._cache or filename not in cls._locks:
			return False;

		with cls._locks[filename]:
			with open(filename, 'wb') as f:
				pickle.dump(cls._cache[filename], f);

		return True;

	@classmethod
	def close_cache(cls, filename):
		cls.sync_cache(filename);
		del cls._cache[filename];
		del cls._locks[filename];