## Game Mechanics

The goal of the game is to maximize your amusement park's value within 100 days. As the manager of the park, you perform one action at the start of each day. The park then opens, and guests interact with the park for a full day.

You begin with only yellow subclasses unlocked; other attractions must be researched.

There are seven primary components to the game:
- **The Park:** Defined by a 20x20 grid. Has an entrance and exit connected by a path. Your park also has a *rating* that reflects guest satisfaction, park upkeep, and overall park quality.
- **Terrain:** Three kinds — Paths, Water, and Empty.
- **Rides:** Core of the park; draw guests in. Three subtypes: Carousels, Ferris Wheels, and Roller Coasters.
- **Shops:** Cater to guest needs. Three subtypes: Drink, Food, and Specialty.
- **Staff:** Maintain your park. Three subtypes: Janitors, Mechanics, and Specialists.
- **Subclasses & Research:** Each ride, shop, and staff subtype has four subclasses — yellow, blue, green, red. Higher subclasses must be unlocked through research.
- **Guests:** Interact with your park, spending money on tickets, food, drinks, and more.

---

### Terrain
- **Empty tiles:** Blank tiles on which something can be built.
- **Path tiles:** Used by guests to move around your park. All attractions must be placed on an empty tile adjacent to a path tile.
- **Water tiles:** Each water tile adjacent to a ride increases that ride's excitement by 1.

---

### Rides
Rides are the core of your amusement park. They are the primary driver in determining how many guests visit your park, they improve guest happiness, and contribute to the overall value of the park. Rides have several key attributes:
- **Capacity:** How many guests can fit on the ride at one time. Capacity also affects how frequently the ride operates. The cumulative capacity of your park is also a key factor in how many guests visit the park.
- **Excitement:** How thrilling the ride is. Higher excitement scores increase guest happiness and park rating.
- **Intensity:** How intense the ride experience is. Keeping the average intensity balanced (around 5) ensures your park caters to a wide range of guests and improves your rating.
- **Ticket price:** The amount guests must pay to ride. If a guest cannot afford the ticket, they are rejected, which decreases their happiness.
- **Cost per operation:** The amount it costs each time the ride runs.

> **TIP:** Building multiple rides of the same kind (i.e., identical subtype and subclass) yields diminishing returns for your park rating. Diversifying your attractions will lead to a higher overall rating.

Rides only operate if guests have boarded. After the first guest boards, rides wait a few turns to allow more guests to join. This waiting time is longer for rides with higher capacity but decreases as more guests board. A full ride always operates immediately.

Rides may break down after operating. When broken, they are out of service and will turn away guests, negatively affecting their happiness and your park rating.
> **TIP:** Hire mechanics to fix broken rides promptly.

There are three subtypes of rides:
- **Carousels:** Cheap to build and operate, and they rarely break down. However, they provide limited excitement and capacity.
- **Ferris Wheels:** Intermediate rides with the highest capacities among all subtypes.
- **Roller Coasters:** Expensive but high-value rides that offer the highest excitement and intensity scores, at the cost of frequent breakdowns.

---

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

---

### Staff
Staff are necessary for the smooth operation of your park, ensuring attractions run properly and guests remain satisfied. Multiple staff can occupy and work on the same tile at any given time. All staff have a daily salary, and some incur additional operating costs when performing tasks.

There are three subtypes of staff:
- **Janitors:** Move through the park toward dirty areas. When on dirty tiles, they clean them. Each cleaning action incurs an operating cost.
- **Mechanics:** Move toward rides that are broken down. When they reach a tile with a broken ride, they repair it. The time and operating cost of repairs depend on the ride's building cost and the mechanic(s) performing the repair.
- **Specialists:** Perform different roles based on subclass:
  - Yellow (Clowns): Increases the happiness of guests waiting in line.
  - Blue (Stockers): Restocks shops with low inventory.
  - Green (Park Criers): Informs guests about out-of-service or dirty attractions, as well as current line wait time for rides.
  - Red (Vendors): Provides food and drink to guests waiting in line.

---

### Subclasses & Research
Each ride, shop, and staff subtype has four subclasses, ordered by price: yellow (cheapest), blue, green, and red (most expensive). Generally, more expensive subclasses provide greater benefits.

You begin with only yellow subclasses and must perform research to unlock the rest. Set your research speed (none/slow/medium/fast) and topics (ride/shop/staff subtypes). Research continues daily until you change your settings, run out of funds, or unlock all available subclasses for the chosen topics. If funds run out or all topics are complete, research speed automatically reverts to *none*. Progress is paused, not lost.

Research unlocks subclasses in the following order: blue → green → red. Once a subclass is unlocked, research continues to the next topic in your list.

> **TIP:** If you wanted to unlock the red roller coaster as quickly as possible, set the research speed to *fast* and select only "roller coaster" as your research topic.

Research speed costs:
- **none:** $0/day — research halted.
- **slow:** $2000/day.
- **medium:** $8000/day.
- **fast:** $32000/day.

Research IP added to park value per day:
- **slow:** $1500/day.
- **medium:** $3000/day.
- **fast:** $6000/day.

---

### Guests
Guests are the heart of your park. The number of guests who visit depends on your park's rating and capacity.

**Capacity** determines both how many guests can be in the park at once and how many potential guests consider visiting. Capacity is determined entirely by the cumulative capacity of your rides.
> **TIP:** Since only rides increase capacity, a park with no rides will receive no visitors.

**Park Rating** determines the likelihood that potential guests decide to enter. New guests cannot enter if the park is already at capacity. Park rating increases with the total excitement of the rides and when guests leave the park happy. Park rating decreases when attractions are frequently out of service, the park is dirty, or the average ride intensity is too high or too low.
> **TIP:** Park ratings are calculated at the start of each day. In some cases, it may take a full day for the action you have taken to affect the park. In these cases, the park rating will only be reflected the subsequent day (two days after the action).

Each guest brings a certain amount of money. When they run out of funds or energy, they leave. Each guest also has hunger, thirst, happiness, and energy levels. Hunger and thirst increase over time, while happiness slowly decreases. Hungry guests seek food shops, thirsty guests seek drink shops, and unhappy guests seek rides. If any of these needs become critical, the guest's happiness drops and they may leave the park.
> **TIP:** A guest's hunger and thirst will continue to increase as they wait in lines. Proximity to food and drink options is especially important for high capacity rides that have longer lines.

Guests favor novelty, preferring kinds of attractions they haven't visited before. They also favor nearby attractions but never visit the same attraction twice in a row. Visiting a ride they can't afford or that's out of service reduces their happiness.

Unhappy guests are more likely to litter, reducing cleanliness. Visiting dirty tiles or attractions decreases happiness further. If a ride is too dirty, guests may turn away.

> **TIP:** You can learn more about guests by surveying them using the *survey_guests* action. This reveals why guests left, their needs at departure, and more. You can survey up to 25 guests at a cost of $500 per guest.

---

### Park Value

The total value of the park is the sum of the total money, the money that would be made by selling all constructed attractions (66% of build cost), and a flat amount per day of research. Each day of slow, medium, and fast research adds $1500, $3000, and $6000 respectively to the park's value.

A ride that breaks down incurs a repair cost equal to 4.5% of its building cost.

---

## Action Space

**place** — Place an entity (ride, shop, or staff) in the amusement park
- x, y: position
- type: ride | shop | staff
- subtype: carousel | ferris_wheel | roller_coaster | drink | food | specialty | janitor | mechanic | specialist
- subclass: yellow | blue | green | red
- price: ticket or item price (rides and shops only)
- order_quantity: max inventory per day (shops only)

---
**move** — Move an entity to a new position
- type, subtype, subclass: identify the entity
- x, y: current position
- new_x, new_y: new position

---
**remove** — Remove an entity (rides/shops are sold for 66% of build cost)
- type, subtype, subclass: identify the entity
- x, y: current position

---
**modify** — Change the price and/or order_quantity of a placed ride or shop
- type: ride | shop
- x, y: position
- price: new price
- order_quantity: new max inventory (shops only)

---
**set_research** — Set research speed and topics
- research_speed: none | slow | medium | fast
- research_topics: list from [carousel, ferris_wheel, roller_coaster, drink, food, specialty]

---
**survey_guests** — Retrieve feedback from a sample of guests
- num_guests: number of guests to survey (max 25, costs $500 each)

---
**wait** — Take no action. Avoid this — every idle step is lost value.
