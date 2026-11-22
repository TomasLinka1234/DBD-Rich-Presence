-- Výňatek z Module:Datatable na deadbydaylight.wiki.gg (stav 22. 11. 2026), použito jen pro testy.
-- Obsah wiki je pod licencí CC BY-SA 4.0.
local p = {}
require("Module:Strings")
--techName = technical name kept in english
ccy = {
	{id = 1, name = "Dollar", symbol = '$', gc = false},
}
survivors = {
	--dbdName => name used in DBD API
	--theme = music theme, nill/true = expected, false = not expected
	--{id = , name = "", altName = , gender = , role = "", origin = , actor = "", dlc =}
	{id = 1, name = "Dwight Fairfield", gender = "Man", role = "Nervous Leader", origin = "American", actor = "Ian Chuprun (BHVR)"},
	{id = 2, name = "Meg Thomas", gender = "Woman", role = "Energetic Athlete", origin = "American", actor = "Ingrid Blemur (BHVR)"},
	{id = 3, name = "Claudette Morel", gender = "Woman", role = "Studious Botanist", origin = "Canadian", actor = "Sarah Robinson (BHVR)"},
	{id = 4, name = "Jake Park", altName = "제이크 박 (Korean)", gender = "Man", role = "Solitary Survivalist", origin = "South Korean", actor = "Kevin Boissonneault (BHVR)"},
	{id = 5, name = "Nea Karlsson", gender = "Woman", role = "Urban Artist", origin = "Swedish", actor = "Morgane Ravasi (BHVR)", dlc = 1},
	{id = 6, name = "Laurie Strode", gender = "Woman", role = "Determined Survivor", origin = "American", actor = "Catherine Lecours (BHVR)", dlc = 2},
	{id = 7, name = "Ace Visconti", gender = "Man", role = "Lucky Gambler", origin = "Argentinian of Italian descent", actor = "Sébastien Varas (BVHR)", dlc = {3, 46}},
	{id = 8, name = 'William "Bill" Overbeck', shortName = "Bill Overbeck", gender = "Man", role = "Old Soldier", origin = "American", actor = "Ricardo Gomez (BHVR)", dlc = 16},
	{id = 9, name = "Feng Min", altName = "凤敏 (Chinese)", useLastName = true, gender = "Woman", role = "Focused Competitor", origin = "Chinese", actor = "Bianca Lavric (BHVR)", dlc = {4, 46}},
	{id = 12, name = "Detective David Tapp", shortName = "David Tapp", dbdName = "Detective Tapp", useLastName = true, gender = "Man", role = "Obsessed Detective", origin = "African American", actor = "Dave Blake (BHVR)", dlc = 7},
	{id = 15, name = 'Jeffrey "Jeff" Johansen', shortName = "Jeff Johansen", dbdName = "Jeff Johansen", gender = "Man", role = "Quiet Artist", origin = "Canadian of Norwegian descent", actor = "Filip Ivanovic (BHVR)", dlc = {10, 47}},
	{id = 17, name = "Ashley J. Williams", shortName = "Ash Williams", gender = "Man", role = "Alone Wolf", origin = "American", actor = "Bruce Campbell (Original Actor)", dlc = 18},
	{id = 24, name = "Élodie Rakoto", gender = "Woman", role = "Occult Investigator", origin = "French, Malagasy", actor = "Beatrix Moersch (BHVR)", dlc = {27, 48}, diacritics = true},
	{id = 42, name = "Aestri Yazar & Baermar Uraz", dbdName = "Aestri Yazar", moniker = "Troupe", role = "Bard Troupe", gender = "Woman (Aestri)" .. br .. "Man (Baermar)", origin = "Oerth (D&D World)", actor = "Aestri: Jesse Vilinsky" .. br .. "Baermar: Robbie Daymond" .. br .. "(both Blindlight)", dlc = 52},
}
p.survivors = survivors

killers = {
	-- {id = number, name = "string", realName = "string", altName = "string" or {table = {"string"}}, gender = "string", origin = "string", power = "string", specialAttack = boolean, altAttackNote = "string", weapon = "string",
		--speed = number (%), altSpeed = {table = {number (%), "string"}}, radius = number or {table = {number}}, height = 'char', dlc = number (id), actor = "string" or {table = {"string"}}},
	{id = 1, name = "Trapper", realName = "Evan MacMillan", altName = "Chuckles", gender = "Man", origin = "American", realm = 1, specialAttack = true, altAttackNote = "Trap Catches", weapon = "The Cleaver", speed = 4.6, radius = 32, height = 'T', diff = 1, actor = "Filip Ivanovic (BHVR)"},
	{id = 2, name = "Wraith", realName = "Philip Ojomo", altName = {"Banshee", "Bob"}, gender = "Man", origin = "Nigerian", realm = 2, specialAttack = false, weapon = "Azarov's Skull", speed = {4.6, "Uncloaked"}, altSpeed = {{6.0, "Cloaked"}}, radius = 32, height = 'T', diff = 1, actor = "Filip Ivanovic (BHVR)"},
	{id = 3, name = "Hillbilly", realName = "Max Thompson Jr.", altName = "The Crooked", gender = "Man", origin = "American", realm = 3, specialAttack = true, altAttackNote = "Chainsaw", weapon = "The Hammer", speed = 4.6, altSpeed = {{10.12, "Chainsaw Sprint"}}, radius = 40, height = 'T', diff = 2, actor = "Filip Ivanovic (BHVR)"},
	{id = 4, name = "Nurse", realName = "Sally Smithson", gender = "Woman", origin = "American of English descent", specialAttack = true, altAttackNote = "Lethal Blinks", weapon = "The Bonesaw", speed = 3.85, altSpeed = {{13.33, "Blink"}}, radius = 32, height = 'A', diff = 4, dlc = 1, actor = "Anais Renevey (BHVR)"},
	{id = 5, name = "Shape", realName = "Michael Myers", altName = {"Boogeyman", "Stalker"}, gender = "Man", origin = "American", specialAttack = true, altAttackNote = "Slaughtering Strike", weapon = "Kitchen Knife", speed = {4.2, "Stalker Mode"}, altSpeed = {{4.6, "Pursuer Mode & Evil Incarnate"}}, radius = {{32, "Stalker Mode"}, {16, "Pursuer Mode"}, {32, "Evil Incarnate"}}, height = 'T', diff = 2, dlc = 2, actor = "Frédéric Poirier (BHVR)"},
}
p.killers = killers

p.npcs = {
	{id = 1, name = "Observer"},
}

realms = { --Realm's name, Realm's Abbreviation
	--order of DLC matters. The First one will be used as the one that introduced the realm
	{id = 1, name = "The MacMillan Estate", codeName = "Industrial", abbr = "Ind", location = "Washington State, United States", palette = "Blue", color="4982a2", dlc = 39},
	{id = 2, name = "Autohaven Wreckers", codeName = "Junkyard", abbr = "Jnk", location = "United States", palette = "Green", color="75d277"},
	{id = 3, name = "Coldwind Farm", codeName = "Farm", abbr = "Frm", location = "United States", palette = "Orange", color="fccf6b"},
	{id = 4, name = "Crotus Prenn Asylum", codeName = "Asylum", abbr = "Asy", location = "United States", palette = "Grey with yellowish tint", color="cccfbc", dlc = {1, 8}},
	{id = 7, name = "Léry's Memorial Institute", codeName = "Hospital", abbr = "Hos", location = "Illinois, United States", palette = "Grey with blueish tint", color="92a7ba", dlc = 4, diacritics = true},
	{id = 20, name = "Dvarka Deepwood", codeName = "Umbra", abbr = "Uba", location = "Dvarka Planet", palette = "Purple, Blue", color= "d5755f", dlc = {40, 44}},
	{id = 22, name = "The Subdivisions", codeName = "Liminal", abbr = "Lm", location = "United States"},
}

maps = { --Area meters is not needed to keep as it's 64x of Tile Area
	{id = 1, name = "Coal Tower", altName = "Warehouse", realm = 1,
		variations = {
			{size = 132, release = "1.0.0"},
			{size = 136, release = "7.3.0"},
			{size = 180, release = "8.7.1",     altVarSuffix = "(2v8)"},
		}
	},
	{id = 2, name = "Groaning Storehouse", altName = "Storehouse", realm = 1,
		variations = {
			{size = 156, release = "1.5.2c"},
			{size = 148, release = "7.3.0"},
		}
	},
	{id = 6, name = "Azarov's Resting Place", altName = "Office", realm = 2,
		variations = {
			{size = 176, release = "1.0.0"},
			{size = 184, release = "8.1.1",     altVarSuffix = "(2v8)"},
		}
	},
	{id = 7, name = "Blood Lodge", altName = "Lodge", realm = 2, size = 156, release = "1.0.0"},
	{id = 51, name = "Hartshorne Mall", realm = 22},
}

return p
