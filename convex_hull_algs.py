import numpy as np
from scipy.spatial import ConvexHull
from operator import itemgetter
import itertools
import cdd
from utils import isSingleton_eps, Vertices
from copy import deepcopy


def con2vert(A, b):
    b = np.reshape(b, (len(b), 1))
    concated_matrix = np.append(b, -A, axis=1)

    mat = cdd.Matrix(concated_matrix, number_type='float')
    mat.rep_type = cdd.RepType.INEQUALITY
    poly = cdd.Polyhedron(mat)
    ext = poly.get_generators()

    vertices = []
    rays = []

    if len(ext) == 0:
        vertices, rays, found = None, None, False
        return vertices, rays, found

    found = True
    for i in range(len(ext)):
        element = ext[i]
        if element[0] == 1:
            vertices.append(np.array(element[1:]))
        else:
            rays.append(np.array(element[1:]))
    return Vertices(vertices=vertices), rays, found


def convex_hull(points, aux_indices=None, need_connections=False, need_equations=False):
    def generate_connections(hull, aux_indices=None):
        def generate_connections_from_simplex(simplex):
            connections = list(itertools.combinations(simplex, 2))
            return connections

        def contain_aux_points(simplex, aux_indices):
            if aux_indices is None:
                return False
            aux_indices = set(aux_indices)
            simplex = set(simplex)
            if simplex.intersection(aux_indices):
                return True
            else:
                return False

        vertrex_index = hull.vertices
        n_points = hull.npoints
        mapping = []
        used_index = 0
        for index in range(n_points):
            if index in vertrex_index:
                mapping.append(used_index)
                used_index += 1
            else:
                mapping.append(None)

        simplices = hull.simplices
        connections = []
        non_boundary = []
        for simplex in simplices:
            if not contain_aux_points(simplex, aux_indices):
                simplex_connections = generate_connections_from_simplex(simplex)
                for simplex_connection in simplex_connections:
                    new_connection = (mapping[simplex_connection[0]], mapping[simplex_connection[1]])
                    if new_connection[0] > new_connection[1]:
                        new_connection = (new_connection[1], new_connection[0])
                    if new_connection in connections:
                        non_boundary.append(connections.index(new_connection))
                    else:
                        connections.append(new_connection)
        for non_index in sorted(non_boundary, reverse=True):
            connections.pop(non_index)

        return list(connections)

    hull = ConvexHull(points)
    vertex_index = set(hull.vertices) - set(aux_indices)
    new_vertices = list(itemgetter(*vertex_index)(points))

    connections, equations = None, None

    if need_connections:
        connections = generate_connections(hull, aux_indices=aux_indices)

    if need_equations:
        A = hull.equations[:, :-1]
        b = hull.equations[:, -1]
        equations = {"A": A, 'b': b}

    hull_vertices = Vertices(vertices=new_vertices, connections=connections, equations=equations)

    return hull_vertices


def remove_non_vertex_auxPoint(vertices, need_connections=False, need_equations=False):
    def add_aux_point(points):
        example = vertices[0]
        aux_points = []
        aux_indices = []

        # add within simplex aux points for zero-support dimensions
        support_index = [False for _ in range(len(example))]  # False for non-support, True for support
        for point in points:
            for dim in range(len(point)):
                if point[dim] > 0:
                    support_index[dim] = True
            if all(support_index):
                break

        if not all(support_index):
            for index in range(len(support_index)):
                if not support_index[index]:
                    in_simplex_aux_point = np.zeros(example.shape)
                    in_simplex_aux_point[index] = sum(example)
                    points.append(in_simplex_aux_point)
                    aux_points.append(in_simplex_aux_point)
                    aux_indices.append(len(points) - 1)

        # Add out of simplex aux point
        out_of_simplex_aux_point = np.zeros(example.shape) + sum(example)
        points.append(out_of_simplex_aux_point)
        aux_points = [out_of_simplex_aux_point]
        aux_indices = [len(points) - 1]

        return points, aux_points, aux_indices

    vertices_addApoint, aux_points, aux_indices = add_aux_point(deepcopy(vertices))
    new_vertices = convex_hull(vertices_addApoint, need_connections=need_connections,
                               aux_indices=aux_indices, need_equations=need_equations)
    # enforce simplex
    equations = new_vertices.equations
    new_equations = None
    if need_equations:
        A, b = equations["A"], equations["b"]
        k = None
        for i in range(A.shape[0]):
            elements = set(A[i, :])
            if isSingleton_eps(elements):
                k = i
                break
        b_prime = -b[k]
        A_prime = -A[k, :]
        A = np.append(A, [A_prime], axis=0)
        b = np.append(b, [b_prime], axis=0)
        new_equations = {"A": A, "b": -b}

    hull_vertices = Vertices(new_vertices.vertices, new_vertices.connections, equations=new_equations)
    return hull_vertices


def remove_non_vertex_analytic(vertices, rotation_parameters, need_connections=False, need_equations=False):
    def rotate_points(points):
        o = rotation_parameters["o"]
        A_pseudo_inv = rotation_parameters["A_pseudo_inv"]

        rotated_points = []
        for point in points:
            diff = point - o
            rotated_point = np.matmul(A_pseudo_inv, diff.T)
            rotated_points.append(rotated_point.T)

        return rotated_points

    def rotate_back_points(rotated_points):
        o = rotation_parameters["o"]
        A = rotation_parameters["A"]

        original_points = []
        for rotated_point in rotated_points:
            diff = np.matmul(A, rotated_point.T).T
            point = o + diff
            original_points.append(point)
        return original_points

    rotated_vertices = rotate_points(vertices)
    new_vertices, connections, equations = convex_hull(rotated_vertices, need_connections=need_connections,
                                                       aux_indices=None, need_equations=need_equations)
    final_vertices = rotate_back_points(new_vertices)
    return Vertices(vertices=final_vertices, connections=connections, equations=equations)


def isInHull(point, vertices):
    def isInVertices(point, vertices):
        for vertex in vertices:
            if np.linalg.norm(point - vertex) < 1e-4:
                return True
        return False

    if isInVertices(point, vertices):
        return True

    vertices.append(point)

    hull_vertices = remove_non_vertex_auxPoint(vertices, False)

    if isInVertices(point, hull_vertices):
        return False
    else:
        return True


def intersect(vertices1, vertices2):
    if vertices1.equations is None:
        vertices1_new = remove_non_vertex_auxPoint(vertices1, need_equations=True, need_connections=False)
        equations1 = vertices1_new.equations
    if vertices2.equations is None:
        vertices2_new = remove_non_vertex_auxPoint(vertices2, need_equations=True, need_connections=False)
        equations2 = vertices2_new.equations

    A1, b1 = equations1["A"], equations1["b"]
    A2, b2 = equations2["A"], equations2["b"]

    new_A = np.append(A1, A2, axis=0)
    new_b = np.append(b1, b2, axis=0)

    vertices, rays, found = con2vert(new_A, new_b)

    return vertices, rays, found
