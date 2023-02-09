import json
import os
import sys
from typing import Optional, List
from urllib import request as request

import numpy as np
import torch
from ase.db import connect
from schnetpack.data import AtomsDataFormat, AtomsDataModule, load_dataset
import schnetpack.transform as trn

sys.path.append('../')
from phisnet.training.hamiltonian_dataset import HamiltonianDataset
from phisnet.training.sqlite_database import HamiltonianDatabase


class ASENablaDFT(AtomsDataModule):

    def __init__(self, dataset_name: str = "dataset_train_2k",
                 datapath: str = "database",
                 data_workdir: Optional[str] = "logs",
                 batch_size: int = 2000,
                 transforms: Optional[List[torch.nn.Module]] = [
                  trn.ASENeighborList(cutoff=5.0),
                  trn.RemoveOffsets("energy", remove_mean=True,
                                    remove_atomrefs=False),
                  trn.CastTo32()
                 ],
                 format: Optional[AtomsDataFormat] = AtomsDataFormat.ASE,
                 **kwargs):

        super().__init__(datapath=datapath,
                         data_workdir=data_workdir,
                         batch_size=batch_size,
                         transforms=transforms,
                         format=format,
                         **kwargs)
        self.dataset_name = dataset_name

    def prepare_data(self):
        datapath_with_no_suffix = os.path.splitext(self.datapath)[0]
        suffix = os.path.splitext(self.datapath)[1]
        if not os.path.exists(datapath_with_no_suffix):
            os.makedirs(datapath_with_no_suffix)
        f = open('../links/energy_databases.json')
        data = json.load(f)
        url = data['train_databases'][self.dataset_name]
        f.close()
        self.datapath = (datapath_with_no_suffix +
                         "/" + self.dataset_name +
                         suffix)
        request.urlretrieve(url, self.datapath)
        with connect(self.datapath) as ase_db:
            if not ase_db.metadata:
                ase_db.metadata = {"_distance_unit": "Bohr",
                                   "_property_unit_dict": {"energy":
                                                           "Hartree"}}
            dataset_length = len(ase_db)
            self.num_train = int(dataset_length * 0.9)
            self.num_val = int(dataset_length * 0.1)
        self.dataset = load_dataset(self.datapath, self.format)


class HamiltonianNablaDFT(HamiltonianDataset):

    def __init__(self, datapath="database", dataset_name="dataset_train_2k",
                 max_batch_orbitals=1200,
                 max_batch_atoms=150, max_squares=4802,
                 subset=None, dtype=torch.float32):

        self.dtype = dtype
        if not os.path.exists(datapath):
            os.makedirs(datapath)
        f = open('../links/hamiltonian_databases.json')
        data = json.load(f)
        url = data['train_databases'][dataset_name]
        f.close()
        filepath = datapath + "/" + dataset_name + ".db"
        request.urlretrieve(url, filepath)
        print("done")
        self.database = HamiltonianDatabase(filepath)
        max_orbitals = []
        for z in self.database.Z:
            max_orbitals.append(tuple((int(z), int(l))
                                      for l in self.database.get_orbitals(z)))
        max_orbitals = tuple(max_orbitals)
        self.max_orbitals = max_orbitals
        self.max_batch_orbitals = max_batch_orbitals
        self.max_batch_atoms = max_batch_atoms
        self.max_squares = max_squares
        self.subset = None
        if subset:
            self.subset = np.load(subset)


class NablaDFT:

    def __init__(self, type_of_nn, *args, **kwargs):
        valid = {"ASE", "Hamiltonian"}
        if type_of_nn not in valid:
            raise ValueError("results: type of nn must be one of %r." % valid)
        self.type_of_nn = type_of_nn
        if self.type_of_nn == "ASE":
            self.dataset = ASENablaDFT(*args, **kwargs)
        else:
            self.dataset = HamiltonianNablaDFT(*args, **kwargs)
