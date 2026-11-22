-- Výňatek z Module:Datatable/Cosmetics na deadbydaylight.wiki.gg (stav 22. 11. 2026), použito jen pro testy.
-- Obsah wiki je pod licencí CC BY-SA 4.0.
local str = require("Module:Strings")
local p = {}

p.cosChars = {
    {id = 1, killer = 7,        rarity = 7, name = "Look-See",          gender = "Man", origin = "n/a",               actor = "No unique voice"},
    {id = 2, killer = 6,        rarity = 4, name = "Birch",             gender = "Woman", origin = "n/a",               actor = "No unique voice"},
    {id = 3, killer = 8,        rarity = 12, name = "Mordeo",            gender = "Woman", origin = "n/a",               actor = "No unique voice"},
    {id = 4, killer = 1,        rarity = 5, name = "Krampus",           gender = "Man", origin = "Central/Eastern European Folkore",  actor = "No unique voice"},
    {id = 5, killer = 18,       rarity = 5, name = "Minotaur",          gender = "Man", origin = "Greek Mythology",   actor = "No unique voice", theme = true},
    {id = 28, killer = 1,       rarity = 7, name = "Naughty Bear",      gender = "Man", origin = "Perfection Island",   actor = "Naughty Bear: David Osborne (BHVR, Original Voice Actor)" .. br .. "Narrator: Ashley Pannell (BHVR, Original Voice Actor)", article = false, theme = true},
    {id = 29, killer = 34,      rarity = 7, name = "Good Gal",          realName = "Tiffany Valentine", gender = "Woman", origin = "American",  actor = "Jennifer Tilly (Blindlight, Original Actress)", theme = true},
    {id = 30, killer = 7,       rarity = 7, name = "Pharaoh Eddie",     gender = "Man", origin = "English", actor = "No unique voice", article = false, theme = true},
    {id = 35, survivor = 36,    rarity = 7, name = "Tubarão",           realName = "Isaac Nunes Oliveira", gender = "Trans Man", origin = "Portuguese",  actor = "Emmett Preciado (Blindlight, Original Voice Actor)"},
    {id = 58, killer = 28,      rarity = 7, name = "Half Spirits' Torments",   gender = "Men/Women", origin = "Japanese", actor = "No unique voice", article = false, theme = true},
    {id = 89, killer = 30,      rarity = 4, name = "Eredin Bréacc Glas",  gender = "Man", origin = "Tir ná Lia", actor = "No unique voice", article = false, theme = true},
    {id = 104, survivor = 22,   rarity = 7, name = "Shimizu Hinako",  gender = "Woman", origin = "Japanese", actor = "Suzie Yeung (Original Voice Actress)", theme = true},
    {id = 108, survivor = 9,    rarity = 7, name = "2B",       gender = "Woman", origin = "Japanese", actor = "Yui Ishikawa (Original Voice Actress)"},
    {id = 120, killer = 40,     rarity = 7, name = "Yellow Rabbit", realName = "William Afton<br>Steve Raglan (alias)", article = false},
}

p.pieces = {
    {id = 1, name = "x"},
}
return p
