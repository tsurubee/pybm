import time
import numpy as np
import torch
import sqapy

class RBM:
    def __init__(self, n_visible=784, n_hidden=2, alpha=0.01, device='cpu'):
        self.n_visible = n_visible
        self.n_hidden  = n_hidden
        self.alpha     = alpha
        self.device    = device

        self.data = None
        self.weight = torch.FloatTensor(self.n_visible, self.n_hidden).uniform_(-1, 1).to(self.device)
        self.b = torch.FloatTensor(self.n_visible).uniform_(-1, 1).to(self.device)
        self.c = torch.FloatTensor(self.n_hidden).uniform_(-1, 1).to(self.device)
        self.energy_records = []

    def train(self, data, n_epochs=2, n_CD=1, sampler="cd"):
        self.energy_records.clear()
        self.data = data
        if sampler == "cd":
            self.__contrastive_divergence(self.data, n_epochs, n_CD)
        elif sampler == "sqa":
            self.__sqa(self.data, n_epochs)
        else:
            pass
        print("Training finished")

    def sample(self, n_iter=5, v_init=None):
        if v_init is None:
            v_init = torch.randint(2, size=(1, self.n_visible)).float().to(self.device)
        v_t = v_init.view(self.n_visible)
        for _ in range(n_iter):
            h_t = self.__forward(v_t)
            v_t = self.__backward(h_t)
        return v_t, h_t

    def __sqa(self, data, n_epochs, batch_size=10000):
        train_time = []
        for e in range(n_epochs):
            self.energy_list = []

            start = time.time()
            for i in range(0, data.shape[0], batch_size):
                batch = data[i:i+batch_size]
                if len(batch) != batch_size:
                    break
                v_0 = batch.mean(axis=0)
                h0_sampled = self.__forward(v_0)
                b = torch.Tensor.numpy(self.b)
                c = torch.Tensor.numpy(self.c)
                weight = torch.Tensor.numpy(self.weight)
                model = sqapy.BipartiteGraph(b, c, weight)
                sampler = sqapy.SQASampler(model, steps=100)
                _, states = sampler.sample()
                v_sampled= torch.from_numpy(np.array(states[0][:len(self.b)])).float()
                h_sampled = torch.from_numpy(np.array(states[0][len(self.b):])).float()

                self.__update_params(v_0, v_sampled, h0_sampled, h_sampled)
                self.energy_list.append(self._energy(v_0, h_sampled).item())

            end = time.time()
            avg_energy = np.mean(self.energy_list)
            print("[epoch {}] takes {:.2f}s, average energy={}".format(
                e, end - start, avg_energy))
            self.energy_records.append(avg_energy)
            train_time.append(end - start)
        print("Average Training Time: {:.2f}".format(np.mean(train_time)))

    def __contrastive_divergence(self, data, n_epochs, n_CD):
        train_time = []
        for e in range(n_epochs):
            self.energy_list = []

            start = time.time()
            for v_0 in data:
                h0_sampled = self.__forward(v_0)
                h_sampled = h0_sampled
                for _ in range(n_CD):
                    v_sampled = self.__backward(h_sampled)
                    h_sampled = self.__forward(v_sampled)

                self.__update_params(v_0, v_sampled, h0_sampled, h_sampled)
                self.energy_list.append(self._energy(v_0, h_sampled).item())

            end = time.time()
            avg_energy = np.mean(self.energy_list)
            print("[epoch {}] takes {:.2f}s, average energy={}".format(
                e, end - start, avg_energy))
            self.energy_records.append(avg_energy)
            train_time.append(end - start)
        print("Average Training Time: {:.2f}".format(np.mean(train_time)))

    def __update_params(self, v_0, v_sampled, h0, h_sampled):
        self.weight += self.alpha * \
                       (torch.matmul(v_0.view(-1, 1), h0.view(1, -1)) -
                        torch.matmul(v_sampled.view(-1, 1), h_sampled.view(1, -1)))
        self.b += self.alpha * (v_0 - v_sampled)
        self.c += self.alpha * (h0 - h_sampled)

    def __forward(self, v):
        p_h = torch.sigmoid(
            torch.matmul(torch.t(self.weight), v) + self.c)
        return self.__sampling(p_h)

    def __backward(self, h):
        p_v = torch.sigmoid(torch.matmul(self.weight, h) + self.b)
        return self.__sampling(p_v)

    def __sampling(self, p):
        dim = p.shape[0]
        true_list = torch.rand(dim).to(self.device) <= p
        sampled = torch.zeros(dim).to(self.device)
        sampled[true_list] = 1
        return sampled

    def _energy(self, v, h):
        return - torch.dot(self.b, v) - torch.dot(self.c, h) \
               - torch.matmul(torch.matmul(torch.t(v), self.weight), h)
