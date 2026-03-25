const tableBody = document.querySelector("tbody");
const fromInput = document.querySelectorAll('input[type="date"]')[0];
const toInput = document.querySelectorAll('input[type="date"]')[1];

const studentId = localStorage.getItem("student_id");
const studentName = localStorage.getItem("student_name");

// Set student name (make sure HTML has id="studentName")
const nameElement = document.querySelector(".name");
if (nameElement && studentName) {
  nameElement.innerText = studentName;
}

// FETCH DATA FROM BACKEND
async function fetchAttendance(fromDate = "", toDate = "") {

  if (!studentId) {
    alert("Please login again!");
    window.location.href = "login.html";
    return;
  }

  let url = `http://127.0.0.1:5000/api/student/attendance?student_id=${studentId}`;

  if (fromDate && toDate) {
    url += `&from_date=${fromDate}&to_date=${toDate}`;
  }

  try {
    const response = await fetch(url);
    const data = await response.json();
    loadTable(data);
  } catch (error) {
    console.error("Error fetching attendance:", error);
  }
}

// LOAD TABLE
function loadTable(data) {

  tableBody.innerHTML = "";

  if (!data || data.length === 0) {
    tableBody.innerHTML =
      `<tr><td colspan="10">No attendance found</td></tr>`;
    return;
  }

  data.forEach(record => {

    let row = `<tr><td>${formatDate(record.date)}</td>`;

    // Ensure 9 hours always
    for (let i = 0; i < 9; i++) {
      const hour = record.hours[i] || "";

      let className = "";
      if (hour === "P") className = "p";
      if (hour === "A") className = "a";

      row += `<td class="${className}">${hour}</td>`;
    }

    row += "</tr>";
    tableBody.innerHTML += row;
  });
}

// FILTER
function filterAttendance() {
  fetchAttendance(fromInput.value, toInput.value);
}

// RESET
function resetFilter() {
  fromInput.value = "";
  toInput.value = "";
  fetchAttendance();
}

// FORMAT DATE
function formatDate(dateStr) {
  const d = new Date(dateStr);
  return d.toLocaleDateString("en-GB");
}

// INITIAL LOAD
fetchAttendance();