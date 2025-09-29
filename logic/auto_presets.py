# -*- coding: utf-8 -*-
"""
auto_presets.py — набір готових пресетів для еквалайзера/ефектів.
"""

def get_auto_eq_presets():
    return [
        # ===== BAR =====
        {"name":"Clean Bar", "eq":{
            "mode":"bar","engine":"freqs","fscale":"log","bars":96,
            "height":420,"thickness":4,"opacity":92,"mirror":True,"baseline":True,"y_offset":0,"color":"#FFFFFF"}},
        {"name":"Bar Neon Mint", "eq":{
            "mode":"bar","engine":"freqs","fscale":"log","bars":128,
            "height":420,"thickness":4,"opacity":90,"mirror":True,"baseline":False,"y_offset":-10,"color":"#89FFC2"}},
        {"name":"Bar Violet", "eq":{
            "mode":"bar","engine":"freqs","fscale":"sqrt","bars":160,
            "height":380,"thickness":5,"opacity":88,"mirror":True,"baseline":True,"y_offset":-6,"color":"#A78BFA"}},
        {"name":"Bar Ice Blue", "eq":{
            "mode":"bar","engine":"freqs","fscale":"lin","bars":96,
            "height":360,"thickness":3,"opacity":95,"mirror":False,"baseline":True,"y_offset":0,"color":"#9BE2FF"}},
        {"name":"Bar Sunset", "eq":{
            "mode":"bar","engine":"freqs","fscale":"log","bars":192,
            "height":400,"thickness":3,"opacity":90,"mirror":True,"baseline":False,"y_offset":-4,"color":"#FFB86B"}},
        {"name":"Bar Deep Blue", "eq":{
            "mode":"bar","engine":"freqs","fscale":"log","bars":224,
            "height":420,"thickness":2,"opacity":92,"mirror":True,"baseline":True,"y_offset":0,"color":"#7CC4FF"}},

        # ===== LINE =====
        {"name":"Line Thin", "eq":{
            "mode":"line","engine":"waves","fscale":"lin","bars":160,
            "height":360,"thickness":2,"opacity":92,"mirror":True,"baseline":True,"y_offset":0,"color":"#E6F1FF"}},
        {"name":"Line Soft Pink", "eq":{
            "mode":"line","engine":"waves","fscale":"sqrt","bars":192,
            "height":420,"thickness":3,"opacity":92,"mirror":True,"baseline":False,"y_offset":-6,"color":"#FFD1E8"}},
        {"name":"Line Citrus", "eq":{
            "mode":"line","engine":"waves","fscale":"log","bars":160,
            "height":360,"thickness":3,"opacity":90,"mirror":True,"baseline":True,"y_offset":0,"color":"#FFE680"}},

        # ===== DOTS =====
        {"name":"Dots Soft", "eq":{
            "mode":"dot","engine":"waves","fscale":"sqrt","bars":128,
            "height":360,"thickness":3,"opacity":96,"mirror":True,"baseline":False,"y_offset":0,"color":"#FFDDEE"},
         "stars":{"enabled":True,"count":800,"intensity":85,"size":2,"color":"#FFFFFF"}},
        {"name":"Dots Night", "eq":{
            "mode":"dot","engine":"waves","fscale":"log","bars":160,
            "height":420,"thickness":4,"opacity":92,"mirror":True,"baseline":True,"y_offset":-8,"color":"#B0E1FF"},
         "stars":{"enabled":True,"count":1200,"intensity":90,"size":2,"color":"#D7EAFE"}},
        {"name":"Dots Minimal", "eq":{
            "mode":"dot","engine":"waves","fscale":"lin","bars":96,
            "height":300,"thickness":2,"opacity":90,"mirror":False,"baseline":True,"y_offset":0,"color":"#FFFFFF"}},

        # ===== DARK / NEON =====
        {"name":"Neon Mint", "eq":{
            "mode":"bar","engine":"freqs","fscale":"log","bars":128,
            "height":420,"thickness":4,"opacity":92,"mirror":True,"baseline":False,"y_offset":-8,"color":"#70FFBF"}},
        {"name":"Cyber Blue", "eq":{
            "mode":"line","engine":"waves","fscale":"log","bars":192,
            "height":420,"thickness":2,"opacity":94,"mirror":True,"baseline":False,"y_offset":0,"color":"#00E0FF"}},
        {"name":"Amber Glow", "eq":{
            "mode":"bar","engine":"freqs","fscale":"sqrt","bars":128,
            "height":360,"thickness":3,"opacity":94,"mirror":True,"baseline":True,"y_offset":-4,"color":"#FFBE55"}},
    ]
