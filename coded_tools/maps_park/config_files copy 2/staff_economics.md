# Specialist subtypes: yellow=clown, blue=stocker, green=park_crier, red=vendor.

## janitor/yellow
salary: 25
clean_rate: 0.028
cleaning_threshold: 0.85
notes: "Cleans tiles."

## janitor/blue
salary: 100
clean_rate: 0.075
cleaning_threshold: 0.95
notes: "Cleans tiles fast, walks fast."

## janitor/green
salary: 500
clean_rate: 0.2
cleaning_threshold: 1.0
notes: "Cleans tiles faster, walks fast."

## janitor/red
salary: 2000
clean_rate: 0.35
cleaning_threshold: 1.2
notes: "Cleans tiles fastest, walks fast. Provides preventative cleaning."

## mechanic/yellow
salary: 15
repair_rate: 2
notes: "Repairs rides."

## mechanic/blue
salary: 100
repair_rate: 8
notes: "Repairs rides fast, walks fast."

## mechanic/green
salary: 250
repair_rate: 20
notes: "Repairs rides faster, walks fast."

## mechanic/red
salary: 1000
repair_rate: 50
notes: "Repairs rides fastest, walks fast. Provides preventative maintenance."

## specialist/yellow
salary: 60
happiness_boost: 0.25
notes: "Clown. Entertains guests in ride lines."

## specialist/blue
salary: 350
stocking_rate: 0.1
max_inventory: 100
restock_threshold: 0.25
idle_ticks: 30
notes: "Stocker. Restocks shops."

## specialist/green
salary: 250
notes: "Park crier. Informs guests about dirty or out-of-service attractions."

## specialist/red
salary: 300
happiness_boost: 0.2
hunger_reduction: 0.3
thirst_reduction: 0.4
notes: "Vendor. Provides food and drink to guests waiting in line."
