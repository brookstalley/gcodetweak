import pygcode

from pygcode.machine import Position, Machine
from pygcode.words import str2word
from pygcode.block import words2gcodes
from pygcode import Line, GCode, Word
from pygcode.exceptions import *
from pygcode.gcodes import (
    GCodeAbsoluteDistanceMode, GCodeIncrementalDistanceMode,
    GCodeAbsoluteArcDistanceMode, GCodeIncrementalArcDistanceMode,
    GCodeCannedCycleReturnPrevLevel, GCodeCannedCycleReturnToR,
)

import os
import re
import math

indir = os.path.normpath("c:/users/brook/onedrive/documents/gcode/")

#infile = "cup5-95x93.gcode"

extrudeMod = False
extrudeModStartZ = 5.0
extrudeModZFreq = 10.0
extrudeModZAmpPct = 0.02

zMod = True
zModStart = 5.0
zModIncreasePerZ = 0.02
zModType="Sine"
zModPerLayer = 6
zCurrentMod = 0.0

myFile = "simple-vase-200x122"

infile = os.path.join(indir,myFile + ".gcode")

paramString = ""
if (zMod):
    paramString = paramString + "-zm{zmt}_{zmpl}_{zmi}".format(zmt=zModType, zmpl = zModPerLayer, zmi = zModIncreasePerZ)
if (extrudeMod):
    paramString = paramString + "-em{emzf}_{emza}".format(emzf=extrudeModZFreq, emza=extrudeModZAmpPct)
print(paramString)

outfile = os.path.join(indir,myFile + paramString + ".gcode")

print("Processing {inf} to {outf}".format(inf = infile, outf=outfile))

m = Machine()

class GCodeExtruderAbsoluteMotion(pygcode.GCode):
    word_key = pygcode.Word('M', 82)

class GCodeExtruderRelativeMotion(pygcode.GCode):
    word_key = pygcode.Word('M', 83)

def extrudeAdjust(curX,curY,curZ,curE,newX,newY,newZ,newE):
    """ Creates periodid (in Z) thinning/thickening of extrusion
    ""  returns new extrusion distance
    """
    if (extrudeMod and (curZ >= extrudeModStartZ)):
        relativeZ = curZ - extrudeModStartZ
        # it should done sin cycle per extrudeModZFreq mm in height
        modPhase = 2*math.pi * relativeZ 
        modAmp = math.sin(modPhase) * extrudeModZAmpPct
        origExtrude = newE - curE
        newExtrude = (1+modAmp) * origExtrude
        return newExtrude
    else:
        return newE

def zAdjust(curX, curY, curZ, curE, origX, origY, origZ, origE):
    global zMod
    """ returns newZ, newE 
    """
    """ Assumes center of piece is at origin (0,0)
    """
    if (zMod and (origZ >= zModStart)):
        #distanceFromCenter = (origX ** 2 + origY ** 2) ** .5
        radians = math.atan2(origY, origX)
        #debug ('Got {r}rad for {x},{y}'.format(r = radians, x=origX, y = origY))
        zModStrength = (origZ - zModStart) * zModIncreasePerZ
        if (zModType == "Sine"):
            sinPhase = math.sin(radians*zModPerLayer)
            zMod = zModStrength * sinPhase
            newZ = origZ + zMod
        else:
            print("Unknown zModType: {zm}".format(zm=zModType))
            return origZ, origE
        origMoveDistance = math.sqrt((origX - curX)**2 + (origY - curY)**2 + (origZ - curZ)**2)
        newMoveDistance = math.sqrt((origX - curX)**2 + (origY - curY)**2 + (newZ - curZ)**2)
        distRatio = newMoveDistance / origMoveDistance
        #print("origE: {oe}, curE: {ce:.5f}, dr: {dr}, nmd: {nmd}, omd: {omd}".format(oe = origE, ce = curE, dr = distRatio, nmd = newMoveDistance, omd = origMoveDistance))
        newE = ((origE - curE) * distRatio) + curE
        #debug("Adding {z}, adjusting E from {oe} to {ne}".format(z = zMod, oe=origE, ne=newE))
        return newZ, newE
    else:
        return origZ, origE

def debug(message):
    print(message)
    return False

with open(infile, 'r') as fhIn:
    fhOut = open(outfile, 'w')
    lineNumber = 0
    layerBands = False
    changedZ = False
    curE = float(0)
    prevX = float(0)
    prevY = float(0)
    prevZ = float(0)
    prevE = float(0)
    lastZ = float(0)
    for line_text in fhIn.readlines():

        lineNumber = lineNumber + 1
        line = Line(line_text)
        #print(line)
        if (line.comment is not None):
                debug("{line}: {comment}".format(line = lineNumber, comment = line.comment))
        
        if (line.block.words is not None):
            
            hasX = False
            hasY = False
            hasZ = False
            hasE = False
            origX = float(0)
            origY = float(0)
            origZ = float(0)
            origE = float(0)

            for word in line.block.words:
                if word.letter == "X":
                    hasX = True
                    origX = float(word.value)
                if word.letter == "Y":
                    hasY = True
                    origY = float(word.value)
                if word.letter == "Z":
                    hasZ = True
                    origZ = float(word.value)
                    lastZ = origZ # save in 
                if word.letter == "E":
                    hasE = True
                    origE = float(word.value)
                if word.letter == "G":
                    if word.value == 92:
                        prevE = 0                   
            if (hasX and hasY and hasE):
                newX = origX
                newY = origY
                if (hasZ):
                    newZ = origZ
                else:
                    origZ = lastZ
                    newZ = lastZ
                    #debug("@@{z}".format(z=lastZ))
                newE = origE
                newZ, newE = zAdjust(m.abs_pos.X, m.abs_pos.Y, m.abs_pos.Z, prevE, origX, origY, origZ, origE)
               
                if (layerBands):
                    newE = extrudeAdjust(m.abs_pos.X, m.abs_pos.Y, m.abs_pos.Z, prevE, newX, newY, newZ, newE)

                if (newE < 0):
                    newE = origE/2
                if (newE < prevE):
                    newE = prevE
                    #print("retraction")
                if (newZ != origZ):
                    changedZ = True                    
                for word in line.block.words:
                    if word.letter == "X":
                        word.value = "{:.3f}".format(newX)
                    if word.letter == "Y":
                        word.value = "{:.3f}".format(newY)
                    if word.letter == "Z":
                        word.value = "{:.3f}".format(newZ) 
                    if word.letter == "E":
                        word.value = "{:.4f}".format(newE)
                if (not hasZ):
                    inferZ = "Z{:.3f}".format(newZ)
                    sw = str2word(inferZ)
                    #debug(sw)
                    line.block.words.append(sw)
                    (line.block.gcodes, line.block.modal_params) = words2gcodes(line.block.words)
                    #debug("! from {lt} to {ln} using {iz}".format(lt = line_text, ln = str(line), iz = inferZ))
                #debug("*** X: {X} -> {nX}, Y: {Y} -> {nY}, Z: {Z} -> {nZ}, E: {E} -> {nE}".format(X = origX, Y=origY, Z= origZ, E=origE, nX = newX, nY = newY, nZ = newZ, nE = newE))
                if (origZ != newZ) or (not hasZ):
                    line.comment = "; z {oz} to {nz}".format(oz=origZ, nz=newZ)
                prevX = newX
                prevY = newY
                prevZ = newZ
                prevE = newE
        try:
            m.process_block(line.block)
        except MachineInvalidState:
            #debug("here")
            continue
        finally:
            # if we've started messing with Z, only allow output lines that have X, Y, AND Z (or don't have any movement)
            print(str(line), file = fhOut)