import SwiftUI

/// A SwiftUI view that displays the patient's entire medical record in a searchable, sectioned list.
/// It uses a `NavigationSplitView` to create a master-detail interface with a sidebar for navigation.
struct RecordsView: View {
    // MARK: - Environment and State
    
    /// Access to the global application state, used to check if the database is ready.
    @EnvironmentObject var appState: AppState
    /// The view model that fetches, holds, and filters the medical record data.
    @StateObject private var viewModel = RecordsViewModel()
    
    /// State to track which table/section is currently selected in the sidebar.
    @State private var selection: String?

    // MARK: - Body
    
    var body: some View {
        /// A three-column navigation interface, ideal for master-detail layouts on larger screens.
        NavigationSplitView {
            // The first column (sidebar) for selecting a record category.
            List(viewModel.tableNames, id: \.self, selection: $selection) { tableName in
                Text(tableName).tag(tableName) // The tag is used to identify the selection.
            }
            .navigationSplitViewColumnWidth(min: 180, ideal: 200)
            .navigationTitle("Tables")
        } detail: {
            // The second column (main content) which displays the details.
            NavigationStack {
                Group {
                    // Conditionally display content based on the app's state.
                    if !appState.isDatabaseReady {
                        PlaceholderView(
                            imageName: "icloud.slash",
                            title: "Database Not Ready",
                            subtitle: "Please go to the 'Importer' tab to create or open a database file."
                        )
                    } else if viewModel.isLoading {
                        ProgressView("Loading Records...")
                    } else if viewModel.clinicalRecord == nil {
                        PlaceholderView(
                            imageName: "questionmark.folder",
                            title: "No Records Found",
                            subtitle: "The database is open but contains no patient records."
                        )
                    } else {
                        // If everything is ready, display the main record list.
                        recordList
                    }
                }
                .navigationTitle("Medical Records")
                .onAppear {
                    viewModel.setup(appState: appState)
                    // Set an initial selection for the sidebar if one isn't already set.
                    if selection == nil {
                        selection = viewModel.tableNames.first
                    }
                }
            }
        }
    }
    
    // MARK: - Subviews
    
    /// The main scrollable list that displays all sections of the medical record.
    private var recordList: some View {
        // `ScrollViewReader` provides a proxy to programmatically scroll to any view with an ID.
        ScrollViewReader { proxy in
            List {
                // A dedicated section for the patient's demographic information.
                Section("Patient Information") {
                    if let patient = viewModel.clinicalRecord?.patient {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(patient.fullName).font(.title2.bold())
                            Text("DOB: \(patient.dob ?? "N/A") | MRN: \(patient.mrn ?? "N/A")")
                            Text("Gender: \(patient.gender ?? "N/A") | Race: \(patient.race ?? "N/A")")
                        }
                        .padding(.vertical, 8)
                    }
                }
                
                // Each `Group` contains a call to the `createSection` helper to build a section for a specific data type.
                // This keeps the body of the List clean and organized.
                Group {
                    createSection(title: "Problems",for: viewModel.filteredProblems) { problem in
                        Text(problem.problemName ?? "N/A").bold()
                        Text("Onset: \(problem.onsetDate ?? "N/A") | Status: \(problem.status ?? "N/A")")
                    }
                }
                
                Group {
                    createSection(title: "Medications", for: viewModel.filteredMedications) { med in
                        Text(med.medicationName ?? "N/A").bold()
                        Text(med.instructions ?? "No instructions")
                        Text("Started: \(med.startDate ?? "N/A") | Status: \(med.status ?? "N/A")")
                    }
                }

                Group {
                    createSection(title: "Allergies", for: viewModel.filteredAllergies) { allergy in
                        Text(allergy.substance ?? "N/A").bold()
                        Text("Reaction: \(allergy.reaction ?? "N/A") | Status: \(allergy.status ?? "N/A")")
                    }
                }
                
                Group {
                    createSection(title: "Lab Results", for: viewModel.filteredLabResults) { result in
                        Text(result.testName ?? "N/A").bold()
                        Text("Result: \(result.value ?? "") \(result.unit ?? "") | Range: \(result.referenceRange ?? "N/A")")
                        if let interpretation = result.interpretation { Text("Interpretation: \(interpretation)").italic() }
                    }
                }
                
                Group {
                    createSection(title: "Procedures", for: viewModel.filteredProcedures) { proc in
                        Text(proc.procedureName ?? "N/A").bold()
                        Text("Date: \(proc.date ?? "N/A") | Provider: \(proc.provider ?? "N/A")")
                    }
                }
                
                Group {
                    createSection(title: "Immunizations", for: viewModel.filteredImmunizations) { imm in
                        Text(imm.vaccineName ?? "N/A").bold()
                        Text("Administered: \(imm.dateAdministered ?? "N/A")")
                    }
                }
                
                Group {
                    createSection(title: "Vitals", for: viewModel.filteredVitals) { vital in
                        Text(vital.vitalSign ?? "N/A").bold()
                        Text("\(vital.value ?? "N/A") \(vital.unit ?? "") | Date: \(vital.effectiveDate ?? "N/A")")
                    }
                }
                
                Group {
                    createSection(title: "Notes", for: viewModel.filteredNotes) { note in
                        Text(note.noteTitle ?? "N/A").bold()
                        Text("Type: \(note.noteType ?? "N/A") | Date: \(note.noteDate ?? "N/A")")
                        Text(note.noteContent ?? "No content.").lineLimit(3)
                    }
                }
            }
            .searchable(text: $viewModel.searchText, prompt: "Search All Records")
            // When the sidebar selection changes, scroll the list to the corresponding section.
            .onChange(of: selection) { newSelection in
                print("Selection changed to: \(newSelection ?? "nil")")
                
                guard let newSelection else { return }
                
                print("Attempting to scroll to ID: '\(newSelection)'")
                
                // Use DispatchQueue to ensure the scroll happens after the UI has updated.
                DispatchQueue.main.async {
                    withAnimation {
                        proxy.scrollTo(newSelection, anchor: .top)
                    }
                }
            }
        }
    }
    
    /// A generic helper function to reduce repetitive code when creating the list sections.
    /// It takes a title, a data array, and a closure for building the row content.
    @ViewBuilder
    private func createSection<T: MedicalRecord & Identifiable, Content: View>(
        title: String,
        for data: [T],
        @ViewBuilder rowContent: @escaping (T) -> Content
    ) -> some View {
        // Only create the section if the corresponding data array is not empty.
        if !data.isEmpty {
            Section(title) {
                ForEach(data) { item in
                    VStack(alignment: .leading, spacing: 2) {
                        rowContent(item)
                    }
                    .padding(.vertical, 4)
                }
            }
            // Assign an ID to the section that matches the sidebar selection tag.
            .id(title)
        }
    }
}
