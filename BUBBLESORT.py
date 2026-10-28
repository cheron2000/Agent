def bubble_sort(arr):
    """Sort flights in place by ticket price using bubble sort."""
    n = len(arr)
    for i in range(n):
        for j in range(0, n - i - 1):
            if arr[j][1] > arr[j + 1][1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
        print("pass-", i)
        print(arr)
    return arr


def selection_sort(arr):
    """Sort flights in place by ticket price using selection sort."""
    n = len(arr)
    for i in range(n):
        min_idx = i
        for j in range(i + 1, n):
            if arr[j][1] < arr[min_idx][1]:
                min_idx = j
        arr[i], arr[min_idx] = arr[min_idx], arr[i]
        print("pass-", i)
        print(arr)
    return arr


def linear_search(arr, flight_no):
    """Return the index of a flight number, or -1 if it is not present."""
    for i in range(len(arr)):
        if arr[i][0] == flight_no:
            return i
    return -1


def main():
    flights = []
    number_of_flights = int(input("Enter total number of Flights: "))

    for i in range(number_of_flights):
        print("\nEnter details of Flight", i + 1)
        flight_no = int(input("Enter Flight Number: "))
        destination = input("Enter Destination: ")
        price = float(input("Enter Ticket Price: "))
        flights.append([flight_no, price, destination])

    while True:
        print("\n\n--------------------MENU--------------------\n")
        print("1. Bubble Sort by Ticket Price")
        print("2. Selection Sort by Ticket Price")
        print("3. Search Flight by Flight Number")
        print("4. Display All Flights")
        print("5. Exit\n")

        choice = int(input("Enter your Choice (from 1 to 5): "))

        if choice == 1:
            bubble_sort(flights)
            print("Flights Sorted by Ticket Price using Bubble Sort:")
            print(flights)
        elif choice == 2:
            selection_sort(flights)
            print("Flights Sorted by Ticket Price using Selection Sort:")
            print(flights)
        elif choice == 3:
            flight_no = int(input("Enter Flight Number to Search: "))
            result = linear_search(flights, flight_no)

            if result != -1:
                print("Flight Found!")
                print("Flight Number:", flights[result][0])
                print("Ticket Price:", flights[result][1])
                print("Destination:", flights[result][2])
            else:
                print("Flight Not Found!")
        elif choice == 4:
            print("\nFlight Details:")
            for flight in flights:
                print(
                    "Flight Number:",
                    flight[0],
                    "Ticket Price:",
                    flight[1],
                    "Destination:",
                    flight[2],
                )
        elif choice == 5:
            print("Thanks for using this program!")
            break
        else:
            print("!!Wrong Choice!!")

        answer = input("Do you want to continue (yes/no): ")
        if answer.lower() != "yes":
            print("Thanks for using this program!")
            break


if __name__ == "__main__":
    main()
