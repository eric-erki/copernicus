#!/usr/bin/env python

# This file is part of Copernicus
# http://www.copernicus-computing.org/
# 
# Copyright (C) 2011, Sander Pronk, Iman Pouya, Erik Lindahl, and others.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as published 
# by the Free Software Foundation
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.


import sys
import os
import math
import os.path
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

import cpc.dataflow
from cpc.dataflow import StringValue
from cpc.dataflow import FloatValue
from cpc.dataflow import IntValue
from cpc.dataflow import RecordValue
from cpc.dataflow import ArrayValue


class FEError(cpc.dataflow.ApplicationError):
    pass

def addIteration(inp, out, i):
    """Add one fe calc iteration."""
    out.addInstance('iter_q_%d'%i, 'fe_iteration')
    out.addInstance('iter_lj_%d'%i, 'fe_iteration')
    # connect shared inputs
    # q
    out.addConnection('init_q:out.resources', 'iter_q_%d:in.resources'%i)
    out.addConnection('init_q:out.grompp', 'iter_q_%d:in.grompp'%i)
    out.addConnection('self:sub_out.nsteps', 'iter_q_%d:in.nsteps'%i)
    # lj
    out.addConnection('init_lj:out.resources', 'iter_lj_%d:in.resources'%i)
    out.addConnection('init_lj:out.grompp', 'iter_lj_%d:in.grompp'%i)
    out.addConnection('self:sub_out.nsteps', 'iter_lj_%d:in.nsteps'%i)
    if i==0:
        # connect the inits
        # q
        out.addConnection('init_q:out.path', 'iter_q_%d:in.path'%i )
        # lj
        out.addConnection('init_lj:out.path', 'iter_lj_%d:in.path'%i )
    else:
        # connect the previous iteration
        # q
        out.addConnection('iter_q_%d:out.path'%(i-1), 'iter_q_%d:in.path'%i )
        #out.addConnection('iter_q_%d:out.lambdas'%(i-1), 
        #                  'iter_q_%d:in.lambdas'%i )
        # lj
        out.addConnection('iter_lj_%d:out.path'%(i-1), 'iter_lj_%d:in.path'%i)
        #out.addConnection('iter_lj_%d:out.lambdas'%(i-1), 
        #                  'iter_lj_%d:in.lambdas'%i)
    # connect the outputs
    out.addConnection('iter_q_%d:out.dG'%i, 'self:sub_in.dG_array[%d][0]'%i)
    out.addConnection('iter_lj_%d:out.dG'%i, 'self:sub_in.dG_array[%d][1]'%i)

def decouple(inp, out, relaxation_time):
    pers=cpc.dataflow.Persistence(os.path.join(inp.persistentDir,
                                               "persistent.dat"))

    init=pers.get('init')
    if init is None:
        init=1
        out.addInstance('init_q', 'fe_init')
        out.addInstance('init_lj', 'fe_init')
        # connect them together
        out.addConnection('init_q:out.conf_b', 'init_lj:in.conf')
        # set inputs
        out.setSubOut('endpoint_array[0]', StringValue('vdwq'))
        out.setSubOut('endpoint_array[1]', StringValue('vdw'))
        out.setSubOut('endpoint_array[2]', StringValue('none'))
        out.setSubOut('n_lambdas_init', IntValue(10))
        # this is a rough guess, but shouldn't matter too much:
        out.setSubOut('nsteps', IntValue(20*relaxation_time) )
        out.setSubOut('nsteps_init', IntValue(relaxation_time) )
        #           inp.getInput('relaxation_time')))

        out.addConnection('self:ext_in.conf', 'init_q:in.conf')
        out.addConnection('self:ext_in.grompp', 'init_q:in.grompp')
        out.addConnection('self:ext_in.resources', 'init_q:in.resources')
        out.addConnection('self:sub_out.nsteps_init', 'init_q:in.nsteps')
        out.addConnection('self:ext_in.molecule_name', 
                          'init_q:in.molecule_name')
        out.addConnection('self:sub_out.endpoint_array[0]', 'init_q:in.a')
        out.addConnection('self:sub_out.endpoint_array[1]', 'init_q:in.b')
        out.addConnection('self:sub_out.n_lambdas_init', 'init_q:in.n_lambdas')

        out.addConnection('self:ext_in.grompp', 'init_lj:in.grompp')
        out.addConnection('self:ext_in.resources', 'init_lj:in.resources')
        out.addConnection('self:sub_out.nsteps_init', 'init_lj:in.nsteps')
        out.addConnection('self:ext_in.molecule_name', 
                          'init_lj:in.molecule_name')
        out.addConnection('self:sub_out.endpoint_array[1]', 'init_lj:in.a')
        out.addConnection('self:sub_out.endpoint_array[2]', 'init_lj:in.b')
        out.addConnection('self:sub_out.n_lambdas_init', 'init_lj:in.n_lambdas')
        pers.set('init', init)

    nruns=pers.get('nruns')
    if nruns is None or nruns==0:
        # make the first two. The first one is simply an equilibration run
        nruns=2
        addIteration(inp, out, 0)
        addIteration(inp, out, 1)

    dgOutputsHandled=pers.get('dg_outputs_handled')
    # read in the dG inputs.
    dgArray=inp.getSubnetInput('dG_array')
    dGl=[]
    end=False
    if dgArray is not None:
        nOutputs=0
        for i in range(len(dgArray)):
            sublist=inp.getSubInput('dG_array[%d]'%i)
            if sublist is not None:
                dGsl=[]
                for j in range(len(sublist)):
                    val=inp.getSubInput('dG_array[%d][%d].value'%(i, j))
                    err=inp.getSubInput('dG_array[%d][%d].error'%(i, j))
                    if val is not None and err is not None:
                        dGsl.append( (val, err) )
                    else:
                        end=True
                        break
                dGl.append(dGsl)
            else:
                break
            if end:
                break
    # now count the number of valid inputs
    ndgOutputs=len(dGl)
    nSubVal=0
    if ndgOutputs > 0:
        nSubVal=len(dGl[0])
        for i in range(1, ndgOutputs):
            if len(dGl[i]) != len(dGl[0]):
                ndgOutputs=i
                break
    if ndgOutputs != dgOutputsHandled:
        val=nSubVal*[0.]
        err=nSubVal*[0.]
        totVal=None
        totErr=None
        N=ndgOutputs
        if N>1: # we ignore the first one, as it is an equilibration run
            for i in range(1, ndgOutputs):
                for j in range(nSubVal):
                    val[j] += dGl[i][j][0]
                    err[j] += dGl[i][j][1]*dGl[i][j][1]
            for j in range(nSubVal):
                totVal += val[j]
                totErr += err[j]
                val[j] = val[j]/N
                err[j] = math.sqrt(err[j] / N)
            totVal /= (N*nSubVal)
            totErr = math.sqrt(totErr/(N*nSubVal))
            dgOutputsHandled=ndgOutputs
            precision=inp.getInput('precision')
            if precision is None:
                precision = 1 # default of 1 kJ/mol
            if totErr > precision:
                addIteration(inp, out, nruns)
                nruns += 1
            out.setOut('delta_f.value', FloatValue(totVal))
            out.setOut('delta_f.error', FloatValue(totErr))
    pers.set('dg_outputs_handled', dgOutputsHandled)
    pers.set('nruns', nruns)
    pers.write()
        

