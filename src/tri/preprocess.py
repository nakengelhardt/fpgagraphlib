def edge_dir(i,j, adj_dict):
    if j not in adj_dict[i]:
        return False
    if len(adj_dict[j]) < 2:
        return False
    if len(adj_dict[i]) < len(adj_dict[j]):
        return False
    if len(adj_dict[i]) == len(adj_dict[j]) and i >= j:
        return False
    return True

def num_active_edges(i, adj_dict):
    num_edges = 0
    for j in adj_dict[i]:
        if edge_dir(i, j, adj_dict):
            num_edges += 1
    return num_edges

def sum_active_edges(k, adj_dict):
    num_edges = 0
    for i in adj_dict[k]:
        if edge_dir(k, i, adj_dict):
            num_edges += num_active_edges(i, adj_dict)
    return num_edges

def count_triangles(adj_dict):
    num_triangles = 0
    for i in adj_dict:
        for j in adj_dict[i]:
            if edge_dir(i, j, adj_dict):
                for k in adj_dict[j]:
                    if i != k and k in adj_dict[i] and edge_dir(j, k, adj_dict):
                        num_triangles += 1
    return num_triangles
