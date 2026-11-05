### Project Overview

A concise summary of the problem, goals, scope, and tools behind this project.

#### Problem Statement

A computer-vision based system which uses a depth camera and a set of vibration motors along each wrist to identify obstacles and help the visually impaired avoid physical dangers.

This project will utilize an Intel RealSense Depth Camera, NVIDIA Jetson Orin Nano, ESP32 microcontrollers, small vibration motors, and Batteries for its hardware. Software will be developed to utilize the camera system to identify obstacles. Vibration motors will change intensity and pattern for giving general direction and/or identify specific dangers.


#### Project Goals

The goal by the end of class is to have a working software + hardware proof of concept that can reliably detect obstacles, provide haptic feedback to nearest obstacles, utilize variable vibration intensities, and be fully wearable.

#### Scope of Work

This will be a self-contained device. Self-powered and can be ran completely isolated.

#### Tech Stack

TBD

#### Hardware

Hardware design files live in [`hardware/`](hardware/). All PCB work is done in **KiCad 10**, and enclosures are modeled in **Autodesk Fusion**. See the [hardware README](hardware/README.md) for full details.

```
hardware/
+-- README.md
+-- models/                        3D models for enclosures
|   +-- Wrist Module/
|       +-- Wrist_Module_Enclosure.f3z    Fusion archive (editable source)
|       +-- Wrist Module Enclosure.3mf    Print-ready model (open in a slicer)
|       +-- enclosure.png                 Assembled render
|       +-- enclosure_exploded.png        Exploded render
+-- wrist_module/                  KiCad project for the wrist haptic board
    +-- wrist_module.kicad_pro     Project file (open this in KiCad)
    +-- wrist_module.kicad_sch     Schematic
    +-- wrist_module.kicad_pcb     PCB layout
    +-- wrist_module.kicad_prl     Local KiCad UI settings (per user)
    +-- Prints/                    Exported schematic and board renders
    |   +-- wrist_module.pdf       Schematic (PDF)
    |   +-- wrist_schematic.png    Schematic (PNG, made from the PDF)
    |   +-- wrist_module.png       Front render
    |   +-- pcb_traces.png         PCB layout showing copper traces
    |   +-- wrist_module_back.png  Back render
    +-- Library/                   Third-party symbols and footprints
        +-- 113991054/             Seeed XIAO ESP32C3 symbol, footprint, and 3D model
        +-- OPL_Kicad_Library-master/  Seeed Open Parts Library
```

##### Wrist Module

The wrist module is a small battery-powered board worn on each wrist. It drives up to five vibration motors that signal the direction and type of nearby obstacles.

| Schematic | PCB (front) | PCB (traces) |
| --- | --- | --- |
| ![Wrist module schematic](hardware/wrist_module/Prints/wrist_schematic.png) | ![Wrist module PCB, front](hardware/wrist_module/Prints/wrist_module.png) | ![Wrist module PCB layout with traces](hardware/wrist_module/Prints/pcb_traces.png) |

| Part | Purpose |
| --- | --- |
| Seeed XIAO ESP32-C3 | Microcontroller; controls motor intensity and patterns |
| ULN2003A | Darlington driver array that switches the motors |
| 5 x motor connectors (MOT 1-5) | Vibration motor outputs, each with a 1N5819 flyback diode |
| Battery connector (BATT CONN) | Battery power input |
| PWR SW (SPDT) | Main power switch |
| TOGG BTN | User push button |
| PWR LED | Power indicator |

To open the project, open `hardware/wrist_module/wrist_module.kicad_pro` in KiCad 10. If symbols or footprints show as missing, add the libraries under `hardware/wrist_module/Library/` in **Preferences -> Manage Symbol/Footprint Libraries** (as project-specific libraries).

The board is housed in a two-part 3D-printed enclosure (base and lid, fastened with four cap screws that also hold the PCB). The lid has openings for the push button and power LED, and the base has side cutouts for the connectors and switch. The editable Fusion source (`.f3z`) and a print-ready `.3mf` are in [`hardware/models/Wrist Module/`](hardware/models/Wrist%20Module/).

| Enclosure (assembled) | Enclosure (exploded) |
| --- | --- |
| ![Wrist module enclosure, assembled](hardware/models/Wrist%20Module/enclosure.png) | ![Wrist module enclosure, exploded with PCB](hardware/models/Wrist%20Module/enclosure_exploded.png) |
