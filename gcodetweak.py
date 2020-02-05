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
myFile = "simple-vase-200x122"
infile = os.path.join(indir,myFile + ".gcode")



class GCodeExtruderAbsoluteMotion(pygcode.GCode):
    word_key = pygcode.Word('M', 82)

class GCodeExtruderRelativeMotion(pygcode.GCode):
    word_key = pygcode.Word('M', 83)

def adjustExtrude(mod, modStartZ, curX, curY, curZ, curE, newX, newY, newZ, newE):
    """ 
    Creates periodic (in Z) thinning/thickening of extrusion
    """
    relativeZ = curZ - modStartZ
    # it should done sin cycle per extrudeModZFreq mm in height
    modPhase = 2*math.pi * relativeZ 
    modAmp = math.sin(modPhase) * extrudeModZAmpPct
    origExtrude = newE - curE
    newExtrude = (1+modAmp) * origExtrude 
    return newX, newY, newZ, newExtrude

def adjustZ(mod, modStartZ, curX, curY, curZ, curE, origX, origY, origZ, origE):
    """    
    Assumes center of piece is at origin (0,0)
    """
    #distanceFromCenter = (origX ** 2 + origY ** 2) ** .5
    radians = math.atan2(origY, origX)
    #debug ('Got {r}rad for {x},{y}'.format(r = radians, x=origX, y = origY))
    zModStrength = (origZ - modStartZ) * mod["zModIncreasePerZ"]
    if (mod["zModType"] == "Sine"):
        sinPhase = math.sin(radians * mod["zModPerLayer"])
        zMod = zModStrength * sinPhase
        newZ = origZ + zMod
    else:
        print("Unknown zModType: {zm}".format(zm=mod["zModType"]))
        return origZ, origE
    origMoveDistance = math.sqrt((origX - curX)**2 + (origY - curY)**2 + (origZ - curZ)**2)
    newMoveDistance = math.sqrt((origX - curX)**2 + (origY - curY)**2 + (newZ - curZ)**2)
    distRatio = newMoveDistance / origMoveDistance
    #print("origE: {oe}, curE: {ce:.5f}, dr: {dr}, nmd: {nmd}, omd: {omd}".format(oe = origE, ce = curE, dr = distRatio, nmd = newMoveDistance, omd = origMoveDistance))
    newE = ((origE - curE) * distRatio) + curE
    #debug("Adding {z}, adjusting E from {oe} to {ne}".format(z = zMod, oe=origE, ne=newE))
    return newX, newY, newZ, newE
        
def debug(message):
    print(message)
    return False

def replaceOrAddLetter(l, letter, value):
    found = False
    for word in l.block.words:
        if word.letter == letter:
            word.value = value
            found = True
    if not found:
        addLetter = "{letter}{value}"
        word = str2word(addLetter)
        l.block.words.append(word)
        (l.block.gcodes, l.block.modal_params) = words2gcodes(l.block.words)
        #debug("! from {lt} to {ln} using {iz}".format(lt = line_text, ln = str(line), iz = inferZ))

    return l

def wordHasLetter(w,l):
    if w.letter == l:
        return True,float(w.value)
    return False,False

def getOutputFilename(infile, mods):
    paramString = ""
    for m in mods:
        paramString += m["suffix"]

    outfile = os.path.join(indir,myFile + paramString + ".gcode")
    return outfile

def processFile(infile, mods, modStartZ):
    m = Machine()
    outfile = getOutputFilename(infile, mods)
    print("Processing {inf} to {outf}".format(inf = infile, outf=outfile))
    with open(infile, 'r') as fhIn:
        fhOut = open(outfile, 'w')
        lineNumber = 0
        # Set all initial positions to 0
        curE = prevX = prevY = prevZ = prevE = lastZ = float(0)
        for line_text in fhIn.readlines():
            lineNumber = lineNumber + 1
            line = Line(line_text)
            if (line.comment is not None):
                    debug("{line}: {comment}".format(line = lineNumber, comment = line.comment))
            
            if (line.block.words is not None):   
                hasX = hasY = hasZ = hasE = False
                origX, origY, origZ, origE = float(0)
                for word in line.block.words:
                    isMovement = False
                    if word.letter == "G" and word.value == 1:
                        isMovement = True
                    if (word.letter == "G" & word.value == 92):
                        prevE = 0 # Simplify3D resets E to 0 for each layer, so if we see a G92 we should consider the current position to be 0

                    hasX, origX = wordHasLetter(word,"X")
                    hasY, origY = wordHasLetter(word,"Y")
                    hasZ, origZ = wordHasLetter(word,"Z")
                    hasE, origE = wordHasLetter(word,"E")                 
                    if hasZ:
                        lastZ = origZ # save last seen Z  

                if isMovement:
                    # start by assuming the new XYZE will be the same as in the file
                    newX, newY, newE = origX, origY, origE
                    if (hasZ):
                        newZ = origZ
                    else:
                        # the line didn't specify Z so we have to use the last one we saw
                        origZ = lastZ
                        newZ = lastZ

                    for mod in mods:
                        adjustRoutine = mod["mod"]
                        extrudeOnly = mod["extrudeOnly"]
                        if (newZ >= modStartZ) and hasX and hasY and (hasE or not extrudeOnly):
                            newX, newY, newZ, newE = adjustRoutine(mod, modStartZ, m.abs_pos.X, m.abs_pos.Y, m.abs_pos.Z, prevE, newX, newY, newZ, newE)
                        
                    line = replaceOrAddLetter(line, "X", "{:.3f}".format(newX))
                    line = replaceOrAddLetter(line, "Y", "{:.3f}".format(newY))
                    line = replaceOrAddLetter(line, "Z", "{:.3f}".format(newZ))
                    line = replaceOrAddLetter(line, "E", "{:.4f}".format(newE))
                    
                    #debug("*** X: {X} -> {nX}, Y: {Y} -> {nY}, Z: {Z} -> {nZ}, E: {E} -> {nE}".format(X = origX, Y=origY, Z= origZ, E=origE, nX = newX, nY = newY, nZ = newZ, nE = newE))
                    if (origZ != newZ) or (not hasZ):
                        line.comment = "; z {oz} to {nz}".format(oz=origZ, nz=newZ)

                    prevX, prevY, prevZ, prevE = newX, newY, newZ, newE

            try:
                m.process_block(line.block)
            except MachineInvalidState:
                #debug("here")
                continue
            finally:
                print(str(line), file = fhOut)

def main():
    global infile
    """
    We'll call these mods in order. 
    "mod" points to the routine that will accept the standard input and return the standard output values.
    "extrudeOnly" indicates whehter to only call the mod for moves with extrusion or to call it for all moves
    "suffix" specifies how to modify the output filename to describe the mods applied
    """

    modStartZ = 5.0
    extrudeModZFreq = 10.0
    extrudeModZAmpPct = 0.02

    zModIncreasePerZ = 0.02
    zModType="Sine"
    zModPerLayer = 6

    mods = [
            {
                "mod": adjustZ, 
                "extrudeOnly" : False, 
                "zModType" : zModType,
                "zModPerLayer" : zModPerLayer,
                "zModIncreasePerZ" : zModIncreasePerZ,
                "suffix": "-zm{zmt}_{zmpl}_{zmi}".format(zmt=zModType, zmpl = zModPerLayer, zmi = zModIncreasePerZ) }, 
            {"mod": adjustExtrude, "extrudeOnly": True, "suffix": "-em{emzf}_{emza}".format(emzf=extrudeModZFreq, emza=extrudeModZAmpPct)}]

    processFile(infile, mods, modStartZ)

if __name__ == "__main__":
    main()

