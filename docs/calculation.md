# How it calculates

All entries since the last settlement form one period. The overview shows the balance "as of now"; a settlement freezes it.

| What | How |
|---|---|
| **Rate per km** | per car and period: the car's fuel or charging costs ÷ the car's driven km. Until the settlement it is an estimate, afterwards frozen. Electric cars work the same way: charging at a station or at home is an entry with an amount (and optionally kWh). |
| **Trip** | km × rate, split among the people who bear it (equally or by weights, e.g. 2:1). |
| **Passenger pays** | Someone outside the group pays for a ride. That lowers the cost of the trip for the people who bear it; whoever received the cash passes it on to the group through their balance. Example: trip 30 €, a passenger gives the driver 20 € → the driver bears 10 € themselves. |
| **Other costs** | by km (service, tyres), in equal parts among active members (insurance, tax, vignette), one person, or like a specific trip (parking, toll). |
| **Balance** | paid − share. Rounded to cents with the largest remainder method; the sum is always exactly 0. |
| **Transfers** | the largest debtor pays the largest creditor → at most n−1 transfers. |
| **Carry-over** | Fuel costs of a car without km in the period (and "by km" costs without any km at all) move to the next settlement. |

## Example

Alex and Sam share a car. Alex drives 300 km alone, Sam 100 km alone, and both drive 100 km together. Sam takes a hitchhiker who pays 10 €. Alex pays 100 € for fuel, Sam pays 60 € insurance (split equally).

- Rate: 100 € ÷ 500 km = 0.20 €/km
- Alex: 300 km = 60 €, half of the shared 100 km = 10 €, half of the insurance = 30 € → 100 €; paid 100 € → balance 0
- Sam: 100 km = 20 €, half of the shared trip = 10 €, minus the hitchhiker's 10 € on Sam's trip (credit) plus the 10 € Sam holds in cash, half of the insurance = 30 € → 60 €; paid 60 € → balance 0

## Odometer checks

The start km of a new trip is prefilled with the car's last reading. Overlapping trips are rejected. Gaps ("km not assigned to a trip") are shown and must be confirmed when settling; their cost is spread over the rate per km to everyone. A trip without end km is "running"; it blocks later trips of that car and settling until it is finished.

## Settling

Settling freezes all entries up to the end date. The end date can be neither in the future nor before the previous settlement. Only the latest settlement can be undone, by an admin of the group. All changes are recorded in the audit log.

## Statistics

The statistics page (overview → *Statistics*, or a car's tile) shows one car per year or over all years. It is only for looking at: the settlement never uses these numbers.

| What | How |
|---|---|
| **Driven** | finished trips by their date; running trips do not count yet. |
| **Consumption** | full to full: what was put in after one full tank (or full charge) up to and including the next one, divided by the km between their odometer readings. An interval only counts when every entry in it has a quantity and no entry without an odometer reading falls into its dates – it could belong to the interval or not. Intervals count in the year they end. Charging losses are included, the way you pay for them. |
| **Cost per 100 km** | fuel or charging plus the car's other costs in the period, divided by its km. Costs without a car (e.g. a group's club fee) are not counted. |
| **Price per litre or kWh** | all fuel or charging entries with a quantity: amount ÷ quantity. |
| **Who drove how much** | km of shared trips are split by weight, rounded to whole km so they add up. |
