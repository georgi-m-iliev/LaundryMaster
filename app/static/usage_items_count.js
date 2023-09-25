// JavaScript code to automatically select the label based on the URL parameter
const selectElement = document.getElementById("showCountSelect");

// const selectedOption = (new URLSearchParams(window.location.search)).get("count");
// if (selectedOption) {
//     switch(selectedOption) {
//         case '10':
//             selectElement.selectedIndex = 0;
//             break;
//         case '25':
//             selectElement.selectedIndex = 1;
//             break;
//         case '50':
//             selectElement.selectedIndex = 2;
//             break;
//         case '100':
//             selectElement.selectedIndex = 3;
//             break;
//         case 'All':
//             selectElement.selectedIndex = 4;
//             break;
//     }
// }

// Event listener to handle changes in the dropdown
selectElement.addEventListener("change", function() {
    // Update the URL with the selected option as a query parameter
    const currentURL = new URL(window.location.href);
    currentURL.searchParams.set("items", this.value);
    window.location.href = currentURL.toString();
});