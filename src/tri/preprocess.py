

def direct(adj_dict, i, j):
    if len(adj_dict[j]) < 2:
        return False
    if len(adj_dict[i]) < len(adj_dict[j]):
        return False
    if len(adj_dict[i]) == len(adj_dict[j]) and i > j:
        return False
    return True

def count_triangles(adj_dict):
    num_triangles = 0
    for i in adj_dict:
        for j in adj_dict[i]:
            if direct(adj_dict, i, j):
                for k in adj_dict[j]:
                    if i != k and k in adj_dict[i] and direct(adj_dict, j, k):
                        num_triangles += 1
    return num_triangles
