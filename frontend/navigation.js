function login() {
  const role = document.getElementById("role").value;

  if (role === "student") {
    window.location.href = "student.html";
  } 
  else if (role === "faculty") {
    window.location.href = "faculty.html";
  } 
  else {
    alert("Please select a role");
  }
}
