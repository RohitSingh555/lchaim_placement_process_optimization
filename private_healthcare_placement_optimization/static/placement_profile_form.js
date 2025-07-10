// JavaScript moved from placement_profile_form.html

// Modal open/close
function openPregnancyModal() {
  document.getElementById('pregnancyPolicyModal').classList.remove('hidden');
  document.body.classList.add('overflow-hidden');
  document.getElementById('genderAcknowledgement').disabled = true;
  document.getElementById('waiverSuccessMsg').classList.add('hidden');
}
function closePregnancyModal() {
  document.getElementById('pregnancyPolicyModal').classList.add('hidden');
  document.body.classList.remove('overflow-hidden');
}
// Drag and drop for signature
const dropzone = document.getElementById('signatureDropzone');
const fileInput = document.getElementById('pregnancy_signature_file');
const preview = document.getElementById('signaturePreview');
const errorDiv = document.getElementById('signatureError');
const dropText = document.getElementById('signatureDropText');
let signatureFile = null;
function showSignaturePreview(file) {
  preview.innerHTML = '';
  if (!file) return;
  const reader = new FileReader();
  reader.onload = function(e) {
    const img = document.createElement('img');
    img.src = e.target.result;
    img.alt = 'Signature Preview';
    img.className = 'max-h-32 rounded shadow mb-2';
    preview.appendChild(img);
    // Remove button
    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.textContent = 'Remove';
    removeBtn.className = 'mt-1 px-3 py-1 bg-red-500 text-white rounded hover:bg-red-600 text-xs font-semibold';
    removeBtn.onclick = function() {
      signatureFile = null;
      fileInput.value = '';
      preview.innerHTML = '';
      dropText.classList.remove('hidden');
    };
    preview.appendChild(removeBtn);
  };
  reader.readAsDataURL(file);
  dropText.classList.add('hidden');
}
dropzone.addEventListener('dragover', function(e) {
  e.preventDefault();
  dropzone.classList.add('border-teal-600', 'bg-teal-100');
});
dropzone.addEventListener('dragleave', function(e) {
  e.preventDefault();
  dropzone.classList.remove('border-teal-600', 'bg-teal-100');
});
dropzone.addEventListener('drop', function(e) {
  e.preventDefault();
  dropzone.classList.remove('border-teal-600', 'bg-teal-100');
  const file = e.dataTransfer.files[0];
  handleSignatureFile(file);
});
dropzone.addEventListener('click', function(e) {
  if (e.target === dropzone) fileInput.click();
});
fileInput.addEventListener('change', function() {
  const file = fileInput.files[0];
  handleSignatureFile(file);
});
function handleSignatureFile(file) {
  errorDiv.classList.add('hidden');
  if (!file) return;
  if (!file.type.startsWith('image/')) {
    errorDiv.textContent = 'Only image files are allowed.';
    errorDiv.classList.remove('hidden');
    fileInput.value = '';
    return;
  }
  if (file.size > 2 * 1024 * 1024) {
    errorDiv.textContent = 'File size must be 2MB or less.';
    errorDiv.classList.remove('hidden');
    fileInput.value = '';
    return;
  }
  signatureFile = file;
  showSignaturePreview(file);
}
document.getElementById('pregnancySignatureForm').addEventListener('submit', function(e) {
  e.preventDefault();
  let valid = true;
  if (!signatureFile) {
    errorDiv.textContent = 'Signature image is required.';
    errorDiv.classList.remove('hidden');
    valid = false;
  } else {
    errorDiv.classList.add('hidden');
  }
  const dateInput = document.getElementById('signed_on_date');
  const dateError = document.getElementById('dateError');
  if (!dateInput.value) {
    dateError.textContent = 'Date is required.';
    dateError.classList.remove('hidden');
    valid = false;
  } else {
    dateError.classList.add('hidden');
  }
  if (!valid) return false;
  const formData = new FormData();
  formData.append('pregnancy_signature_file', signatureFile);
  formData.append('signed_on_date', dateInput.value);
  fetch('/update-pregnancy-signature/', {
    method: 'POST',
    headers: {
      'X-Requested-With': 'XMLHttpRequest',
      'X-CSRFToken': (document.querySelector('[name=csrfmiddlewaretoken]') || {}).value || ''
    },
    body: formData
  })
  .then(response => response.json().then(data => ({status: response.status, body: data})))
  .then(({status, body}) => {
    if (body.success) {
      document.getElementById('genderAcknowledgement').disabled = false;
      document.getElementById('waiverSuccessMsg').classList.remove('hidden');
      closePregnancyModal();
    } else if (body.errors) {
      if (body.errors.pregnancy_signature_file) {
        errorDiv.textContent = body.errors.pregnancy_signature_file;
        errorDiv.classList.remove('hidden');
      }
      if (body.errors.signed_on_date) {
        dateError.textContent = body.errors.signed_on_date;
        dateError.classList.remove('hidden');
      }
    }
  })
  .catch(() => {
    errorDiv.textContent = 'An error occurred. Please try again.';
    errorDiv.classList.remove('hidden');
  });
  return false;
});
document.getElementById('waiverSaveBtn').addEventListener('click', function(e) {
  e.preventDefault();
  let valid = true;
  if (!signatureFile) {
    errorDiv.textContent = 'Signature image is required.';
    errorDiv.classList.remove('hidden');
    valid = false;
  } else {
    errorDiv.classList.add('hidden');
  }
  const dateInput = document.getElementById('signed_on_date');
  const dateError = document.getElementById('dateError');
  if (!dateInput.value) {
    dateError.textContent = 'Date is required.';
    dateError.classList.remove('hidden');
    valid = false;
  } else {
    dateError.classList.add('hidden');
  }
  if (!valid) return false;
  const formData = new FormData();
  formData.append('pregnancy_signature_file', signatureFile);
  formData.append('signed_on_date', dateInput.value);
  fetch('/update-pregnancy-signature/', {
    method: 'POST',
    headers: {
      'X-Requested-With': 'XMLHttpRequest',
      'X-CSRFToken': (document.querySelector('[name=csrfmiddlewaretoken]') || {}).value || ''
    },
    body: formData
  })
  .then(response => response.json().then(data => ({status: response.status, body: data})))
  .then(({status, body}) => {
    if (body.success) {
      document.getElementById('genderAcknowledgement').disabled = false;
      document.getElementById('waiverSuccessMsg').classList.remove('hidden');
      closePregnancyModal();
    } else if (body.errors) {
      if (body.errors.pregnancy_signature_file) {
        errorDiv.textContent = body.errors.pregnancy_signature_file;
        errorDiv.classList.remove('hidden');
      }
      if (body.errors.signed_on_date) {
        dateError.textContent = body.errors.signed_on_date;
        dateError.classList.remove('hidden');
      }
    }
  })
  .catch(() => {
    errorDiv.textContent = 'An error occurred. Please try again.';
    errorDiv.classList.remove('hidden');
  });
  return false;
});

function selectGender(gender) {
  const options = ["Male", "Female", "Other", "Prefer not to say"];
  options.forEach((opt) => {
    const el = document.getElementById("gender-" + opt);
    if (el) {
      el.classList.remove(
        "bg-teal-500",
        "text-white",
        "border-teal-600",
        "shadow-lg"
      );
      el.classList.add("border-teal-300", "hover:bg-teal-100");
    }
  });

  const selectedTile = document.getElementById("gender-" + gender);
  if (selectedTile) {
    selectedTile.classList.add(
      "bg-teal-500",
      "text-white",
      "border-teal-600",
      "shadow-lg"
    );
    selectedTile.classList.remove(
      "border-teal-300",
      "hover:bg-teal-100"
    );
  }

  document.getElementById("gender").value = gender;
  document.getElementById("genderError").classList.add("hidden");

  const pregnancyNotice = document.getElementById("pregnancyNotice");
  const checkbox = document.getElementById("genderAcknowledgement");
  const nextButton = document.getElementById("nextstep_2");
  const signedOnDate = document.getElementById("signed_on_date");

  if (gender === "Female") {
    pregnancyNotice.classList.remove("hidden");
    checkbox.checked = false;
    checkbox.disabled = true;
    nextButton.disabled = true;
    if (signedOnDate) signedOnDate.required = true;
  } else {
    pregnancyNotice.classList.add("hidden");
    checkbox.checked = true;
    checkbox.disabled = false;
    nextButton.disabled = false;
    if (signedOnDate) signedOnDate.required = false;
  }
}

function toggleNextButton() {
  const checkbox = document.getElementById("genderAcknowledgement");
  const gender = document.getElementById("gender").value;
  const nextButton = document.getElementById("nextstep_2");

  if (gender === "Female") {
    nextButton.disabled = !checkbox.checked;
  } else {
    nextButton.disabled = false;
  }
}

// ... (continue with the rest of the JS blocks in order) ...
// The rest of the JS blocks from placement_profile_form.html should be appended here, preserving order and logic. 