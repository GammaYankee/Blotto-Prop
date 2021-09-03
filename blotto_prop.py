import numpy as np
from mpl_toolkits import mplot3d
import matplotlib.pyplot as plt
from scipy.spatial import ConvexHull, convex_hull_plot_2d
from operator import itemgetter
from shapely.geometry import Polygon
from copy import deepcopy
from utils import Vertices, isEqual


class BlottoProp:
    def __init__(self, connectivity, x0, agent_name, T=50, eps=0, hull_method="aux_point"):
        self.connectivity = connectivity
        self.N = len(self.connectivity)
        self.x0 = x0
        self.X = sum(x0)
        self.T = T
        self.agent_name = agent_name

        self.vertex_flow = [Vertices([self.x0], None)]
        self.extreme_actions = self.generate_extreme_actions()

        self.o, self.A, self.A_pseudo_inv = self._init_coordinate_transferer()
        self.eps = eps
        self.hull_method = hull_method

        # print initial point

    # def prop_T(self): # propogate the whole T steps
    #     self.plot_feasible_region(self.vertex_flow[0], 0)
    #
    #     for t in range(self.T - 1):
    #         new_vertices = []
    #         for x in self.vertex_flow[t-1]:
    #             new_vertices += self._prop_vertex(x)
    #
    #         new_vertices = self._remove_non_vertex(new_vertices)
    #         self.vertex_flow.append(new_vertices)
    #
    #         self.plot_feasible_region(new_vertices, t + 1)

    def __len__(self):
        return len(self.vertex_flow)

    def append_flow(self, vertices: Vertices):
        self.vertex_flow.append(vertices)

    def override_flow(self, vertices: Vertices):
        self.vertex_flow[-1] = vertices

    def revert_step(self):
        self.vertex_flow.pop()

    def prop_step(self):  # propagate one step
        new_vertices = []
        for x in self.vertex_flow[-1].vertices:
            new_vertices += self._prop_vertex(x)
        if self.hull_method == "aux_point":
            new_vertices, connection = self._remove_non_vertex_auxPoint(new_vertices)
        else:
            new_vertices, connection = self._remove_non_vertex_analytic(new_vertices)

        return Vertices(new_vertices, connection)

    def cut(self, vertices, cut_vertices):

        current_vertices = vertices

        cut_vertices_rotate = self._rotate_points(cut_vertices.vertices)
        current_vertices_rotate = self._rotate_points(current_vertices.vertices)

        p1 = Polygon(cut_vertices_rotate)
        p2 = Polygon(current_vertices_rotate)

        p_new = p1.intersection(p2)

        # plot projected geometries
        # plt.plot(*p1.exterior.xy)
        # plt.plot(*p2.exterior.xy)
        # plt.plot(*p_new.exterior.xy)
        #
        # plt.show()

        new_points_tmp = p_new.exterior.coords.xy
        new_points_rotated = [np.array([new_points_tmp[0][i], new_points_tmp[1][i]]) for i in
                              range(len(new_points_tmp[0]) - 1)]
        new_points = self._rotate_back_points(new_points_rotated)
        new_connections = self._gen_standard_connection(len(new_points))

        # self.vertex_flow[-1] = Vertices(new_points, new_connections)

        return Vertices(new_points, new_connections)

    def req_2_simplex(self, x_req):
        assert sum(x_req) < 1
        cut_points = []

        for i in range(self.N):
            cut_vertex = deepcopy(x_req)
            cut_vertex[i] = 1 - sum(x_req) + x_req[i]  # cut_vertex = 1 - sum_{k!=i} x_req[i]
            cut_points.append(cut_vertex)

        connections = self._gen_standard_connection(self.N)

        return Vertices(cut_points, connections)

    def _gen_standard_connection(self, n):
        connections = []
        for i in range(n):
            if i + 1 <= n - 1:
                connections.append([i, i + 1])
            else:
                connections.append([i, 0])
        return connections

    def _prop_vertex(self, x):
        new_vertices = []
        for extreme_actions in self.extreme_actions:
            new_vertices.append(np.matmul(x, extreme_actions))
        return new_vertices

    def _remove_non_vertex_auxPoint(self, vertices):
        vertices_addApoint, aux_point = self._add_point(vertices)
        new_vertices, connections = self._convex_hull(vertices_addApoint)
        final_vertices, final_connections = self._remove_aux_point(new_vertices, connections, aux_point)
        return final_vertices, final_connections

    def _remove_non_vertex_analytic(self, vertices):
        rotated_vertices = self._rotate_points(vertices)
        new_vertices, connections = self._convex_hull(rotated_vertices)
        final_vertices = self._rotate_back_points(new_vertices)
        return final_vertices, connections

    def _convex_hull(self, points):
        hull = ConvexHull(points)
        vertex_index = hull.vertices
        new_vertices = list(itemgetter(*vertex_index)(points))
        connections = [
            np.concatenate((np.where(vertex_index == simplex[0])[0], np.where(vertex_index == simplex[1])[0])) for
            simplex in hull.simplices]
        return new_vertices, connections

    def _add_point(self, points):
        aux_point = np.zeros(self.x0.shape) + self.X
        points.append(aux_point)
        return points, aux_point

    def _remove_aux_point(self, points, connections, aux_point):
        for index, point in enumerate(points):
            if all(abs(point - aux_point) < 1e-5):
                target = index
                break
        points.pop(target)

        remove_index = []
        for index, connection in enumerate(connections):
            if connection[0] == target or connection[1] == target:
                remove_index.append(index)
            if connection[0] > target:
                connection[0] -= 1
            if connection[1] > target:
                connection[1] -= 1
        for index in remove_index:
            connections.pop(index)

        return points, connections

    def _rotate_points(self, points):
        o = self.o
        A_pseudo_inv = self.A_pseudo_inv

        rotated_points = []
        for point in points:
            diff = point - o
            rotated_point = np.matmul(A_pseudo_inv, diff.T)
            rotated_points.append(rotated_point.T)

        return rotated_points

    def _rotate_back_points(self, rotated_points):
        o = self.o
        A = self.A

        original_points = []
        for rotated_point in rotated_points:
            diff = np.matmul(A, rotated_point.T).T
            point = o + diff
            original_points.append(point)
        return original_points

    def generate_extreme_actions(self):
        return self._expand(0, list=[np.array([])])

    def _expand(self, n, list):
        n_children = sum(self.connectivity[n, :])
        non_zero_indices = np.nonzero(self.connectivity[n, :])[0]

        for i in range(len(list)):
            current_list = list.pop(0)

            for j in range(n_children):
                new_row = np.zeros(self.N)
                new_row[non_zero_indices[j]] = 1
                if n > 0:
                    new_action = np.vstack((current_list, new_row))
                else:
                    new_action = new_row
                list.append(new_action)

        if n == self.N - 1:
            return list
        else:
            list = self._expand(n + 1, list)

        return list

    def plot_simplex(self, t, color='b'):

        r = self.X

        plt.figure(figsize=(6, 6), dpi=120)

        ax = plt.axes(projection='3d')
        ax.view_init(azim=50, elev=45)

        xline = np.linspace(0, r, 20)
        yline = r - xline
        zline = np.linspace(0, 0, 20)
        ax.plot3D(xline, yline, zline, color + '-', label="simplex")

        xline = np.linspace(0, 0, 20)
        yline = np.linspace(0, r, 20)
        zline = r - yline
        ax.plot3D(xline, yline, zline, 'b-')

        xline = np.linspace(0, r, 20)
        yline = np.linspace(0, 0, 20)
        zline = r - xline
        ax.plot3D(xline, yline, zline, 'b-')

        ax.set_xlim3d(0, r + 0.1)
        ax.set_ylim3d(0, r + 0.1)
        ax.set_zlim3d(0, r + 0.1)

        plt.title("Agent {} feasible region at time {}".format(self.agent_name, t), fontsize=20)

        return ax

    def _init_coordinate_transferer(self):
        o = np.zeros(self.N)
        o[0] = self.X

        A = np.zeros((self.N, self.N - 1))
        for i in range(1, self.N):
            A[i, i - 1] = 1
            A[0, i - 1] = -1

        A_pseudo_inv = np.linalg.pinv(A)

        return o, A, A_pseudo_inv
