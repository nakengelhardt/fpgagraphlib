import random
import time
from graph import *


def random_edge_cut(graph, num_pe):
	for node in graph.nodes:
		node.home = random.randrange(num_pe)

def random_vertex_cut(graph, num_pe):
	pe_nodes = [set() for i in range(num_pe)]
	for edge in graph.edges:
		home = random.randrange(num_pe)
		edge.home = home
		for node in edge.source, edge.sink:
			if node.home == None:
				node.master = home
				node.home = {}
			node.home[home] = None
			pe_nodes[home].add(node)
	return pe_nodes



def breadth_first_search(graph, startNode):
	"""
	Run a BFS on graph starting from startNode.
	"""
	q = deque()
	q.appendleft(startNode)
	startNode.tmp = True
	print("Starting from node " + str(startNode.id))
	while len(q) > 0:
		currentnode = q.pop()
		txt = "Visiting node " + str(currentnode.id) + ". It has neighbors:"
		for nextnode in currentnode.get_neighbors():
			txt += " " + str(nextnode.id)
			if not nextnode.tmp:
				nextnode.tmp = True
				q.appendleft(nextnode)
				txt += "+"
		# print(txt)
	print("Done!")

def distributed_bfs(graph, startNode, num_pe):
	"""
	Run a BFS on graph starting from startNode.
	"""
	random_edge_cut(graph)
	localq = [[] for i in range(num_pe)]
	localq[startNode.home].append(startNode)
	next = [[set() for i in range(num_pe)] for j in range(num_pe)]

	while sum(len(l) for l in localq) > 0:
		# run current iteration
		for i in range(num_pe):
			if len(localq[i]) > 0:
				for currentnode in localq[i]:
					currentnode.tmp = True
					txt = "Visiting node " + str(currentnode.id) + " on PE " + str(currentnode.home) +". It has neighbors:"
					for nextnode in currentnode.get_neighbors():
						txt += " " + str(nextnode.id)
						if nextnode.home == i:
							if not nextnode.tmp:
								next[i][i].add(nextnode)
								txt += "+"
							else:
								txt += "-"
						else:
							next[i][nextnode.home].add(nextnode)
							txt += "?"
					# print(txt)
		# prepare next iteration
		for i in range(num_pe):
			localq[i] = set()
			for j in range(num_pe):
				for n in next[j][i]:
					if not n.tmp:
						localq[i].add(n)
	print("Done!")

def get_active_nodes(nodes):
	active = set()
	for node in nodes:
		if node.active:
			active.add(node)
	return active

def shortest_path(graph, startNode):
	startNode.tmp = 0
	for node in startNode.get_neighbors():
		node.active = True
	while get_active_nodes(graph.nodes):
		for node in get_active_nodes(graph.nodes):
			new_tmp = node.tmp if node.tmp != None else float("inf")
			for neighbor in node.get_incidents():
				if neighbor.tmp != None and neighbor.tmp + node.neighbors[neighbor].weight < new_tmp:
					new_tmp = neighbor.tmp + node.neighbors[neighbor].weight
			if node.tmp == None or new_tmp < node.tmp:
				node.tmp = new_tmp
				for neighbor in node.get_neighbors():
					neighbor.active = True
			node.active = False



				






def main():
	if len(sys.argv) < 2:
		print("Usage: {} graph_file".format(sys.argv[0]))
		return
	with open(sys.argv[1]) as graph_file:
		graph = Graph(from_file=graph_file, directed=False)
		random.seed(27)
		num_pe = 3
		startNode = random.choice(graph.nodes)
		before = time.perf_counter()
		shortest_path(graph, startNode)
		# breadth_first_search(graph, startNode)
		# distributed_bfs(graph, startNode, num_pe)
		after = time.perf_counter()
		print("Execution took {:2f} seconds.".format(after-before))
		print("Source: " + str(startNode))
		for node in graph.nodes:
			print(str(node) +": at distance " + str(node.tmp) + " from source.")
		# num_not_visited = 0
		# for node in graph.nodes:
		# 	if not node.tmp:
		# 		num_not_visited += 1
		# if num_not_visited:
		# 	print(str(num_not_visited) + " out of " + str(len(graph.nodes)) + " nodes were not visited.")

if __name__ == '__main__':
	import sys
	main()