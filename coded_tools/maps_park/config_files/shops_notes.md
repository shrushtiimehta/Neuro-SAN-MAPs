### Shops
Shops are necessary to adequately cater to guest needs, and provide additional value to a park. Shops have several key attributes:
- **Order quantity:** The amount of inventory purchased at the start of each day. Unsold inventory is lost at the end of the day.
- **Item cost:** The cost of purchasing one unit of inventory.
- **Item price:** The price guests pay for one unit of inventory.

At the start of each day, shops are stocked according to their order quantity at the item cost. If there are insufficient funds to fully restock all shops, partial stocking will occur. If a shop runs out of inventory during the day, it will go out of service, turning away guests and lowering their happiness and your park rating.  
> **TIP:** Leave enough funds after your action so your shops can be adequately restocked.  
> **TIP:** Order quantity can be updated using the *modify* action.

There are three subtypes of shops:
- **Drink:** Sells beverages that quench guests' thirst.
- **Food:** Sells food that satisfies guests' hunger.
- **Specialty:** Provides unique services based on subclass:
  - Yellow (Souvenir Shops): Boosts guest happiness.
  - Blue (Info Booths): Informs guests about attractions and their prices.
  - Green (ATMs): Allows guests to withdraw additional funds.
  - Red (Billboards): Encourages guests to seek food and ATMs.

By default, guests do not actively seek out Specialty Shops; they visit them only if they pass by.  
> **TIP:** Place specialty shops in high-traffic areas to increase the likelihood of guest interaction.

## Shop Notes

- Any existing shop can be sold for a fraction of its building cost.
- Per-tier numeric stats are reported in the observation envelope.

### Subclass-specific effects

**Drink Shops**
- *Green drink shops:* in addition to quenching thirst, provide a boost to guest happiness.
- *Red drink shops:* caffeinate guests, boosting energy and allowing them to move twice as fast for a number of steps.

**Food Shops**
- *Green food shops:* both satiate hunger and quench thirst.
- *Red food shops:* sell luxury food — greatly satiate hunger and increase happiness.

**Specialty Shops** *(guests will not target specialty shops; they only visit if they walk adjacent to one)*
- *Yellow (Souvenir Shop):* happiness boost on first purchase, diminishing with each subsequent souvenir.
- *Blue (Information Booth):* informs guests about attractions; ensures guests only visit rides within their budget and preferences.
- *Green (ATM):* lets guests withdraw additional money; the amount withdrawn decreases exponentially with each subsequent withdrawal, down to a minimum.
- *Red (Billboard):* makes guests more hungry, thirsty, and happy; resets the visit count of attractions (so guests are more likely to revisit) and, if the guest is below a money threshold, directs them to an ATM.
