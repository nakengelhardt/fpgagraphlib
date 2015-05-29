

class GraphError(RuntimeError):
	pass


class Node:
	"""
	Node class.

	Nodes can have a weight, a temporary value to assist with computations/algorithms, and attached data.
	"""
	num_nodes = 0

	def __init__(self, weight=1.0, tmp=None, data=None, home=None):
		Node.num_nodes += 1
		self.id = Node.num_nodes
		self.weight = weight
		self.tmp = tmp
		self.data = data
		self.home = home
		self.neighbors = {}
		self.incidents = {}
		self.active = False

	def __str__(self):
		return "Node " + str(self.id)

	def get_neighbors(self):
		return self.neighbors.keys()

	def get_incidents(self):
		return self.incidents.keys()


class Edge:
	"""
	Edge class.

	Edges can have a weight, a temporary value to assist with computations/algorithms, and attached data.
	"""
	def __init__(self, source, sink, weight=1.0, tmp=None, data=None, home=None):
		self.source = source
		self.sink = sink
		self.weight = weight
		self.tmp = tmp
		self.data = data
		self.home = home

	def __str__(self):
		return "Edge ({},{})".format(self.source.id, self.sink.id)


class Graph:
	"""
	Graph class.

	Graphs are build of nodes and edges. Graphs can be directed or undirected.
	"""
	def __init__(self, directed=True, from_file=None):
		"""
		Initialize a graph.

		Keyword arguments:
		directed: whether this graph is directed
		from_file: file descriptor to read graph information from. File must be in format supported by import_graph.
		"""
		self.directed = directed
		self.nodes = []
		self.edges = []
		if from_file:
			self.import_graph(from_file)

	def add_node(self, **kwargs):
		"""
		Add a node to this graph.

		Takes the same arguments as the Node() constructor.
		"""
		node = Node(**kwargs)
		self.nodes.append(node)
		return node

	def add_edge(self, source, sink, **kwargs):
		"""
		Add an edge to this graph.

		Takes the same arguments as the Edge() constructor.
		"""
		if sink in source.neighbors:
			return
			# raise GraphError("Edge already exists!")
		edge = Edge(source, sink, **kwargs)
		source.neighbors[sink] = edge 
		sink.incidents[source] = edge
		if not self.directed:
			sink.neighbors[source] = edge
			source.incidents[sink] = edge
		self.edges.append(edge)

	def import_graph(self, from_file):
		"""
		Read the information to build this graph from file.

		from_file: file descriptor to read graph information from.

		from_file should contain lines of either of the following forms:
			nodeID nodeWeight
			sourceID sinkID edgeWeight
		where the IDs can be any string not containing whitespace, and nodeWeight and edgeWeight are floats.
		Nodes that are referenced in an edge but do not have a line assigning a weight get a default weight of 1.0.
		It is not allowed to have two edges from the same source to the same sink node.
		Lines starting with '#' or '//' are ignored.
		"""
		nodes = {}
		for line in from_file:
			line.strip()
			if line.startswith(('#', '//')):
				continue
			args = line.split()
			if len(args) < 2:
				pass
			elif len(args) < 3:
				# assume it's a node
				# node may have been added by reference in an edge, so just update weight if it exists
				node = args[0]
				weight = float(arg[1])
				if node not in nodes:
					nodes[node] = self.add_node()
				nodes[node].weight = weight
			else:
				# it's an edge
				source = args[0]
				sink = args[1]
				weight = float(args[2])
				if source not in nodes:
					nodes[source] = self.add_node()
				if sink not in nodes:
					nodes[sink] = self.add_node()
				self.add_edge(nodes[source], nodes[sink], weight=weight)

	def export_graph(self, to_file=None):
		"""
		If to_file is specified, write a description of this graph into to_file, in a format readable by import_graph.
		Otherwise, return a string describing this graph.
		"""
		ret = ""
		for node in self.nodes:
			ret += "{0} {1}\n".format(node.id, node.weight)
		for edge in self.edges:
			ret += "{} {} {}\n".format(edge.source.id, edge.sink.id, edge.weight)
		if to_file:
			to_file.write(ret)
		else:
			return ret
