import time

class TaskTracker(object):
	"""
	Simple wrapper around a list of task UIDs that prints out the time
	of addition and removal. Can be used as an external Task Group to track
	arbitrary groups of tasks.
	"""
	def __init__(self, engine, name):
		self._tasks = {}
		self._engine = engine
		self._name = name

	def length(self):
		return len(self._tasks)

	def add(self, id):
		self._tasks[id] = time.clock()
		self._engine.log_debug("TaskTracker `%s` added task %s" % (self._name, id))

	def has(self, id):
		return (id in self._tasks)

	def remove(self, id):
		start_time = self._tasks[id]
		del self._tasks[id]
		self._engine.log_debug("TaskTracker `%s` removed task %s after %s seconds" %
			(self._name, id, time.clock() - start_time))

	def clear(self, id):
		self._tasks.clear()
