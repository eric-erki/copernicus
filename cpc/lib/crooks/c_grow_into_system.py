#!/usr/bin/env python

# This file is part of Copernicus
# http://www.copernicus-computing.org/
#
# Copyright (C) 2011-2016, Sander Pronk, Iman Pouya, Magnus Lundborg, Erik Lindahl,
# and others.
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
import shutil
import subprocess
import random
import re
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

import cpc.dataflow
from cpc.dataflow import StringValue
from cpc.dataflow import FloatValue
from cpc.dataflow import IntValue
from cpc.dataflow import BoolValue
from cpc.dataflow import FileValue
from cpc.dataflow import RecordValue
from cpc.dataflow import ArrayValue

from c_pull_fr import genPullMdpParameters

def checkUpdated(inp, items):
    for item in items:
        if inp.getInputValue(item).isUpdated():
            return True
    return False


def getSystemDimensions(groFile):

    dimensions = list()

    with open(groFile) as f:
        lines = f.readlines()

    parts = lines[-1].split()

    for i in range(3):
        dimensions.append(float(parts[i]))

    return dimensions


def getNAtoms(groFile):

    with open(groFile) as f:
        lines = f.readlines()

    nAtoms = int(lines[1])

    return nAtoms


def addToSystem(systemInFile, systemOutFile, moleculeFile, posFileName, nMol):

    # It can take a long time to find a volume large enough to grow in a large molecule using scale > 0.3, but lower
    # than that risks getting bonds through the middle of rings, making the simulation crash.
    scale = 0.275
    match = None
    #while scale >= 0.30:
        #try:
            #os.remove(systemOutFile)
        #except OSError:
            #pass
        #cmdLine=['gmx', 'insert-molecules', '-f', systemInFile, '-ci', moleculeFile, '-ip', posFileName, '-o', systemOutFile, '-nmol', '%d' % nMol,
                 #'-scale', '%f' % scale, '-dr', '1.5', '1.5', '0.15', '-try', '15000', '-allpair']
        #proc=subprocess.Popen(cmdLine,
                              #stdin=subprocess.PIPE,
                              #stdout=subprocess.PIPE,
                              #stderr=subprocess.STDOUT,
                              #close_fds=True)
        #(stdout, stderr)=proc.communicate()

        #if proc.returncode != 0:
            #raise cpc.dataflow.ApplicationError("ERROR: insert-molecules returned %s"%(stdout))

        #match=re.search(r'Added ([0-9.]+) molecules', stdout)

        #if match and int(match.group(1)) == nMol:
            #sys.stderr.write('Inserted %s molecules in system %s with scale %s\n' % (nMol, systemOutFile, scale))
            #return True

        #scale -= 0.01

    try:
        os.remove(systemOutFile)
    except OSError:
        pass
    cmdLine=['gmx', 'insert-molecules', '-f', systemInFile, '-ci', moleculeFile, '-ip', posFileName, '-o', systemOutFile, '-nmol', '%d' % nMol,
             '-scale', '%f' % scale, '-dr', '2.0', '2.0', '0.10', '-try', '30000', '-allpair']
    proc=subprocess.Popen(cmdLine,
                          stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT,
                          close_fds=True)
    (stdout, stderr)=proc.communicate()

    if proc.returncode != 0:
        raise cpc.dataflow.ApplicationError("ERROR: insert-molecules returned %s"%(stdout))

    match=re.search(r'Added ([0-9.]+) molecules', stdout)

    if match and int(match.group(1)) == nMol:
        sys.stderr.write('Inserted %s molecules in system %s with scale %s\n' % (nMol, systemOutFile, scale))
        return True

    return False

def appendToIndexFile(indexFile, systemGroFileName, name, groups):

    if not os.path.isfile(indexFile) or os.stat(indexFile).st_size == 0:
        cmdLine = ['gmx', 'make_ndx', '-f', systemGroFileName, '-o', indexFile]
        proc=subprocess.Popen(cmdLine,
                              stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT,
                              close_fds=True)
        (stdout, stderr)=proc.communicate(input = 'q\n')
        if proc.returncode != 0:
            raise cpc.dataflow.ApplicationError("ERROR: gmx make_ndx returned %s"%(stdout))

    indexFileParts = indexFile.split('.')
    tmpIndexFile = '%s%s.%s' % (''.join(indexFileParts[:-1]), 'tmp', indexFileParts[-1])
    
    # Molecule index groups often get repeated. LIG must point at the first instance when using 'gmx select' below
    with open(indexFile) as f:
        ligGroupNr = -1
        for line in f:
            if line.strip().startswith('[ '):
                ligGroupNr += 1
                if line.strip().startswith('[ LIG ]'):
                    break
        else:
            ligGroupNr = -1
    
    cmdLine = ['gmx', 'select', '-n', indexFile, '-f', systemGroFileName, '-on', tmpIndexFile]
    proc=subprocess.Popen(cmdLine,
                          stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT,
                          close_fds=True)
    (stdout, stderr)=proc.communicate(input = '"not_SOL_not_LIG" group "System" and not group %d and not group "SOL"\n"SOL_not_LIG" group "SOL" and not group %d\n"not_SOL" not group "SOL"\n' % (ligGroupNr, ligGroupNr))
    if proc.returncode != 0:
#        raise cpc.dataflow.ApplicationError("ERROR: gmx select returned %s"%(stdout))
        tmpIndexFile = None

    with open(indexFile, 'a') as f:

        if tmpIndexFile:
            with open(tmpIndexFile) as tmpf:
                for line in tmpf:
                    f.write(line)

        f.write('[ NON_%s ]\n' % name)
        maxIndex = groups[0][0]
        for i in xrange(1, maxIndex, 10):
            string = ' '.join(str(x) for x in xrange(i,min(maxIndex, i+10)))
            f.write('%s\n' % string)
        f.write('[ %s_ALL ]\n' % name)
        for atoms in groups:
            string = ' '.join(str(x) for x in atoms)
            f.write('%s\n' % string)
        for i, atoms in enumerate(groups):
            f.write('[ %s_%d ]\n' % (name, i))
            string = ' '.join(str(x) for x in atoms)
            f.write('%s\n' % string)


def addToTopologyFile(topologyFile, name, n):

    with open(topologyFile, 'a') as f:
        f.write('%s\t%d\n' % (name, n))

def findAtomClosestToCenter(molFile, dimensions):

    centerPosition = (dimensions[0]/2, dimensions[1]/2, dimensions[2]/2)

    with open(molFile) as f:
        lines = f.readlines()

    minDist = None
    minDistIndex = None

    for i, line in enumerate(lines[2:-1]):
        x = float(line[20:28])
        y = float(line[28:36])
        z = float(line[36:44])

        dist = math.sqrt(math.pow(centerPosition[0]-x, 2) + math.pow(centerPosition[1]-y, 2) + math.pow(centerPosition[2]-z, 2))
        if minDist == None or dist < minDist:
            minDist = dist
            minDistIndex = i + 1

    return minDistIndex or 0

def prepareMolSystem(inp, out):

    outDir=inp.getOutputDir()
    persDir=inp.getPersistentDir()
    #fullSystemFileName=os.path.join(outDir, "fullSystemOut.gro")

    dup_x = inp.getInput('n_x_dups_in_sys') or 1
    dup_y = inp.getInput('n_y_dups_in_sys') or 1
    dup_z = inp.getInput('n_z_dups_in_sys') or 1
    nOutputs = inp.getInput('n_outputs') or 1

    molName = inp.getInput('molecule_name') or 'LIG'

    systemGroFileName = inp.getInput('system_conf')
    moleculeGroFileName = inp.getInput('molecule_conf')

    systemDimensions = getSystemDimensions(systemGroFileName)
    moleculeDimensions = getSystemDimensions(moleculeGroFileName)
    moleculeCenterOffset = moleculeDimensions[2]/2
    systemCenterAtom = findAtomClosestToCenter(systemGroFileName, systemDimensions)
    systemNAtoms = getNAtoms(systemGroFileName)
    moleculeNAtoms = getNAtoms(moleculeGroFileName)

    sys.stderr.write('System dimensions are: %f %f %f\n' % (systemDimensions[0], systemDimensions[1], systemDimensions[2]))
    sys.stderr.write('Atom closest to system center is: %d\n' % systemCenterAtom)

    out.setOut('system_center_atom', IntValue(systemCenterAtom))
    out.setOut('system_z_dim', FloatValue(systemDimensions[2]))

    zOffsetInSys = systemDimensions[2]/dup_z

    indexGroups = []

    molPos = [None, None, None]

    posFileName = os.path.join(persDir, 'positions.dat')

    for cnt in xrange(nOutputs):
        for trycnt in range(10):
            fileName = os.path.join(outDir, 'sys_pos_%d.gro' % cnt)
            with open(posFileName, 'w') as f:
                for x in xrange(dup_x):
                    for y in xrange(dup_y):
                        for z in xrange(dup_z):
                            molPos[0] = random.uniform(0, systemDimensions[0])
                            molPos[1] = random.uniform(0, systemDimensions[1])
                            molPos[2] = z * zOffsetInSys # - moleculeCenterOffset
                            f.write('%6.3f   %6.3f   %6.3f\n' % (molPos[0], molPos[1], molPos[2]))
                            sys.stderr.write('Trying to add molecule at pos: %.3f %.3f %.3f\n' % (molPos[0], molPos[1], molPos[2]))

            if addToSystem(systemGroFileName, fileName, moleculeGroFileName, posFileName, dup_x*dup_y*dup_z):
                break
            else:
                sys.stderr.write('Adding molecules failed attempt nr %d.' % (trycnt+1))
                if trycnt < 9:
                    sys.stderr.write('Trying again at new positions.\n')
        else:
            raise Exception('Cannot find enough space to insert molecules')

        out.setSubOut('starting_conf_files[%d]' % cnt, FileValue(fileName))

    currSystemNAtoms = systemNAtoms

    for i in xrange(dup_x*dup_y*dup_z):
        indexGroups.append(range(currSystemNAtoms+1, currSystemNAtoms+moleculeNAtoms+1))
        currSystemNAtoms += moleculeNAtoms

    newIndexFile = os.path.join(outDir, 'index.ndx')
    inpIndexFile = inp.getInput('grompp.ndx')
    if inpIndexFile:
        shutil.copyfile(inpIndexFile, newIndexFile)

    sys.stderr.write('Index groups: %s\n' % indexGroups)
    for i, group in enumerate(indexGroups):
        sys.stderr.write('Index group %d: %s\n' % (i, group))

    appendToIndexFile(newIndexFile, fileName, molName, indexGroups)
    out.setOut('ndx', FileValue(newIndexFile))
    out.setSubOut('n_index_groups', IntValue(len(indexGroups)))

    topFile = os.path.join(outDir, 'topol.top')
    inpTopFile = inp.getInput('grompp.top')
    if inpTopFile:
        shutil.copyfile(inpTopFile, topFile)

    addToTopologyFile(topFile, molName, dup_x * dup_y * dup_z)
    out.setOut('top', FileValue(topFile))


def genInstances(inp, out):

    dup_x = inp.getInput('n_x_dups_in_sys') or 1
    dup_y = inp.getInput('n_y_dups_in_sys') or 1
    dup_z = inp.getInput('n_z_dups_in_sys') or 1
    moleculeGroFileName = inp.getInput('molecule_conf')
    moleculeNAtoms = getNAtoms(moleculeGroFileName)

    sys.stderr.write('Adding mdruns instance\n')
    out.addInstance('runs', 'gromacs::grompp_mdruns')
    out.addConnection('self:sub_out.settings_array', 'runs:in.settings')

#    if moleculeNAtoms < 10:
#        initLambda = 0.40
#    else:
#        initLambda = 0.75

    initLambda = 0.75

    nSteps = inp.getInput('n_steps') or 25000
    if nSteps:
        deltaLambda = -(initLambda)/nSteps
    else:
        deltaLambda = None

    molName = inp.getInput('molecule_name')
    if not molName:
        molName = 'LIG'

    settings_array=[]

    defineStr = inp.getInput('define')

    nOutputs = inp.getInput('n_outputs') or 1

    sys.stderr.write('%d outputs will be generated.\n' % nOutputs)

    for i in range(nOutputs):
        mdp=[]
        #mdp.append(RecordValue( { 'name' : StringValue('dt'),
                                  #'value' : StringValue('0.001') }))
        #mdp.append(RecordValue( { 'name' : StringValue('constraints'),
                                  #'value' : StringValue('all-bonds') }))
        #mdp.append(RecordValue( { 'name' : StringValue('nstlog'),
                                  #'value' : StringValue('2') }))
        #mdp.append(RecordValue( { 'name' : StringValue('nstxout-compressed'),
                                  #'value' : StringValue('2') }))
        mdp.append(RecordValue( { 'name' : StringValue('integrator'),
                                  'value' : StringValue('sd') }))
        mdp.append(RecordValue( { 'name' : StringValue('pcoupl'),
                                  'value' : StringValue('berendsen') }))
        mdp.append(RecordValue( { 'name' : StringValue('nstpcouple'),
                                  'value' : StringValue('1') }))
        mdp.append(RecordValue( { 'name' : StringValue('tau-p'),
                                  'value' : StringValue('1') }))
        mdp.append(RecordValue( { 'name' : StringValue('free-energy'),
                                  'value' : StringValue('yes') }))
        mdp.append(RecordValue( { 'name' : StringValue('init-lambda'),
                                  'value' : StringValue('%.1f' % initLambda) }))
        mdp.append(RecordValue( { 'name' : StringValue('couple-moltype'),
                                  'value' : StringValue(molName) }))
        mdp.append(RecordValue( { 'name' : StringValue('couple-lambda0'),
                                  'value' : StringValue('vdw') }))
        mdp.append(RecordValue( { 'name' : StringValue('couple-lambda1'),
                                  'value' : StringValue('none') }))

#        genPullMdpParameters(mdp, molName, 2, 0, rate=0, constraint=False, pullK=50, nstout=10000)
#        genPullMdpParameters(mdp, molName, 2, 0, rate=0, constraint=False, pullK=2.5, nstout=10000)

        out.addConnection('self:sub_out.starting_conf_files[%d]' % i, 'runs:in.conf[%d]' % i)
        out.addConnection('self:ext_in.grompp.mdp', 'runs:in.mdp[%d]' % i)
        out.addConnection('self:ext_out.ndx', 'runs:in.ndx[%d]' % i)
        out.addConnection('self:ext_out.top', 'runs:in.top[%d]' % i)
        out.addConnection('self:ext_in.grompp.include', 'runs:in.include[%d]' % i)
        out.addConnection('self:ext_in.grompp.mdrun_cmdline_options', 'runs:in.cmdline_options[%d]' % i)
        out.addConnection('self:ext_in.resources', 'runs:in.resources[%d]' % i)
        out.addConnection(None, 'runs:in.priority[%d]' % i, IntValue(5))
        out.addConnection('runs:out.conf[%d]' % i, 'self:ext_out.conf[%d]' % i)

        if deltaLambda:
            mdp.append(RecordValue( { 'name' : StringValue('nsteps'),
                                      'value' : StringValue('%d'%nSteps) }))
            mdp.append(RecordValue( { 'name' : StringValue('delta-lambda'),
                                      'value' : StringValue('%g'%deltaLambda) }))
        if defineStr:
            mdp.append(RecordValue( { 'name' : StringValue('define'),
                                      'value' : StringValue(defineStr) }))

        settings_array.append(ArrayValue(mdp))

    out.setSubOut('settings_array', ArrayValue(settings_array))


def genBoundOutput(inp, out):

    genBoundOut = inp.getInput('gen_bound_fe_output')
    if genBoundOut:
        molName = inp.getInput('molecule_name') or 'LIG'
        systemGroFileName = inp.getInput('system_conf')
        moleculeGroFileName = inp.getInput('molecule_conf')

        sys.stderr.write('Generating conformation for bound FE calculations.\n')

        out.addInstance('gen_bound_conf', 'crooks::grow_gen_bound_conf')
        out.addInstance('gen_bound_conf_equil', 'gromacs::grompp_mdruns')
        out.addConnection('self:sub_out.bound_equil_settings_array', 'gen_bound_conf_equil:in.settings')

        sys.stderr.write('Setting inputs for bound FE calculations.\n')

        out.addConnection('self:ext_in.grompp.ndx', 'gen_bound_conf:in.ndx')
        out.addConnection('self:ext_in.grompp.top', 'gen_bound_conf:in.top')
        out.addConnection('self:ext_in.molecule_name', 'gen_bound_conf:in.molecule_name')
        out.addConnection('runs:out.conf[0]', 'gen_bound_conf:in.conf')

        systemNAtoms = getNAtoms(systemGroFileName)
        moleculeNAtoms = getNAtoms(moleculeGroFileName)

        out.addConnection(None, 'gen_bound_conf:in.sys_n_atoms', IntValue(systemNAtoms))
        out.addConnection(None, 'gen_bound_conf:in.molecule_n_atoms', IntValue(moleculeNAtoms))
        out.addConnection('gen_bound_conf:out.ndx', 'self:ext_out.bound_ndx')
        out.addConnection('gen_bound_conf:out.top', 'self:ext_out.bound_top')

        settings_array=[]
        mdp=[]
        mdp.append(RecordValue( { 'name' : StringValue('nsteps'),
                                  'value' : StringValue('100000') }))
        mdp.append(RecordValue( { 'name' : StringValue('define'),
                                  'value' : StringValue('-DREST_LIG_FE') }))
        settings_array.append(ArrayValue(mdp))
        out.setSubOut('bound_equil_settings_array', ArrayValue(settings_array))

        out.addConnection('gen_bound_conf:out.conf', 'gen_bound_conf_equil:in.conf[0]')
        out.addConnection('gen_bound_conf:out.ndx', 'gen_bound_conf_equil:in.ndx[0]')
        out.addConnection('gen_bound_conf:out.top', 'gen_bound_conf_equil:in.top[0]')
        out.addConnection('self:ext_in.grompp.mdp', 'gen_bound_conf_equil:in.mdp[0]')
        out.addConnection('self:ext_in.grompp.include', 'gen_bound_conf_equil:in.include[0]')
        out.addConnection('self:ext_in.grompp.mdrun_cmdline_options', 'gen_bound_conf_equil:in.cmdline_options[0]')
        out.addConnection('self:ext_in.resources', 'gen_bound_conf_equil:in.resources[0]')
        out.addConnection(None, 'gen_bound_conf_equil:in.priority[0]', IntValue(5))
        
        out.addConnection('gen_bound_conf_equil:out.conf[0]', 'self:ext_out.bound_conf')


def grow(inp, out):
    sys.stderr.write('Starting c_grow_into_system.grow\n')
    pers = cpc.dataflow.Persistence(os.path.join(inp.getPersistentDir(),
                                                 "persistent.dat"))
    init = pers.get('init')

    if init is None:
        init=True
    else:
        inpItems=['grompp', 'system_conf', 'molecule_conf', 'molecule_name',
                  'n_steps', 'n_x_dups_in_sys', 'n_y_dups_in_sys', 'n_z_dups_in_sys',
                  'n_outputs']
        if checkUpdated(inp, inpItems):
            init = True
        else:
            init = False

    if init:
        prepareMolSystem(inp, out)

        genInstances(inp, out)

        genBoundOutput(inp, out)

    pers.set('init', init)


    pers.write()
    sys.stderr.write('Writing persistence\n')

    return out




def grow_gen_bound_conf(inp, out):

    sys.stderr.write('Starting c_grow_into_system.grow_gen_bound_conf\n')

    outDir=inp.getOutputDir()

    systemNAtoms = inp.getInput('sys_n_atoms')
    moleculeNAtoms = inp.getInput('molecule_n_atoms')
    systemGroFileName = inp.getInput('conf')
    molName = inp.getInput('molecule_name')
    if not molName:
        molName = 'LIG'

    fileName = os.path.join(outDir, 'bound.gro')
    sys.stderr.write('Removing all except one instance of the in-grown molecule in file: %s\n' % fileName)

    with open(systemGroFileName) as f:
        lines = f.readlines()

    with open(fileName, 'w') as f:
        f.write(lines[0])
        f.write('%d\n' % (systemNAtoms + moleculeNAtoms))
        for line in lines[2:systemNAtoms + moleculeNAtoms + 2]:
            f.write(line)
        f.write(lines[-1])

    out.setOut('conf', FileValue(fileName))

    newIndexFile = os.path.join(outDir, 'bound.ndx')
    inpIndexFile = inp.getInput('ndx')
    if inpIndexFile:
        shutil.copyfile(inpIndexFile, newIndexFile)

    indexGroups = []
    indexGroups.append(range(systemNAtoms+1, systemNAtoms+moleculeNAtoms+1))

    appendToIndexFile(newIndexFile, fileName, molName, indexGroups)
    out.setOut('ndx', FileValue(newIndexFile))

    boundTopFile = os.path.join(outDir, 'bound_topol.top')
    inpTopFile = inp.getInput('top')
    if inpTopFile:
        shutil.copyfile(inpTopFile, boundTopFile)

    addToTopologyFile(boundTopFile, molName, 1)
    out.setOut('top', FileValue(boundTopFile))