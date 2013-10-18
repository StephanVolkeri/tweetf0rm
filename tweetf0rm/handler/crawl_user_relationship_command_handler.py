#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
RedisCommandHandler: handler that generates new commands on the fly
'''

import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

from .base_handler import BaseHandler
import multiprocessing as mp
import futures, json, copy, time
from tweetf0rm.redis_helper import NodeQueue, NodeCoordinator
from tweetf0rm.utils import full_stack, distribute_to_node
import json

def flush_cmd(bulk, data_type, template, redis_config, verbose=False):

	try:
		node_coordinator = NodeCoordinator(redis_config=redis_config)

		qsizes = node_coordinator.node_qsizes()

		if (verbose):
			logger.info(qsizes)
		
		node_queues = {}

		for element in bulk:
			if data_type == "ids" and type(element) == int:
				user_id = element
			elif data_type =="users" and type(element) == dict and "id" in element:
				user_id = element['id']
			
			t = copy.copy(template)
			t["user_id"] = user_id
			t["depth"] -= 1

			node_id = distribute_to_node(qsizes)[0]

			if (node_id in node_queues):
				node_queue = node_queues[node_id]
			else:
				node_queue = NodeQueue(node_id, redis_config=redis_config)
				node_queues[node_id] = node_queue

			node_queue.put(t)
			qsizes[node_id] += 1

			if verbose:
				logger.info("send [%s] to node: %s"%(json.dumps(t),node_id))

			
	except Exception as exc:
		logger.error('error during flush: %s'%exc)

	return True
		

class CrawlUserRelationshipCommandHandler(BaseHandler):

	def __init__(self, verbose=False, template=None, redis_config = None):
		'''
		A RedisCommandHandler is used to push new commands into the queue;
		this is helpful, in cases such as crawling a user's followers' followers to create a network
		some user has extremely large number of followers, it's impossible (and inefficient) to re-iterate through 
		the follower lists, after it's done... when it flush, it flush the commands to the redis channel
		'''
		super(CrawlUserRelationshipCommandHandler, self).__init__(verbose=verbose)
		self.data_type = template["data_type"]
		self.template = template
		self.redis_config = redis_config

	def need_flush(self, bucket):
		# flush every time there is new data comes in
		return True

	def flush(self, bucket):
		logger.info("i'm getting flushed...")

		with futures.ProcessPoolExecutor(max_workers=1) as executor:
			for k, v in self.buffer[bucket].iteritems():
				for s in v:
					o = json.loads(s)

					f = executor.submit(flush_cmd, o[self.data_type], self.data_type, self.template, self.redis_config, verbose=self.verbose)

					self.futures.append(f)
					# while (f.running()):
					# 	time.sleep(5)
			
			# send to a different process to operate, clear the buffer
			self.clear(bucket)

		True
