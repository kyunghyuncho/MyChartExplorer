// Imports the fundamental Swift library for core functionalities.
import Foundation

/// Defines custom errors that can be thrown during the XML parsing process.
enum ParserError: Error {
    /// The provided URL for the XML file is not valid.
    case invalidURL
    /// An error occurred while trying to load the data from the URL.
    case dataLoadingFailed(Error)
    /// An error occurred during the XML parsing itself, often from the underlying XMLParser.
    case parsingFailed(Error)
    /// The XML was parsed, but essential patient information could not be found.
    case patientDataMissing
}

/// A class responsible for parsing Clinical Document Architecture (CDA) XML files.
/// It uses a delegate-based approach with `XMLParser` to build a custom, navigable tree
/// of `XMLElement` objects, which is then used to extract structured medical data.
class XMLFileParser: NSObject, XMLParserDelegate {

    // MARK: - Properties

    /// Holds the structured medical records extracted from the XML.
    private var parsedRecords: ParsedRecords?
    /// The root element of the parsed XML document tree.
    private var root: XMLElement?
    /// A pointer to the current element being processed by the parser, used to build the tree.
    private var currentElement: XMLElement?
    
    /// This dictionary dynamically stores the mapping from a namespace URI to its prefix (e.g., "urn:hl7-org:v3" -> "cda").
    /// It is populated as the parser encounters `xmlns:` attributes.
    private var namespaceMapping: [String: String] = [:]

    /// A predefined dictionary of common namespaces and their prefixes used for querying the XML tree.
    private let ns = [
        "cda": "urn:hl7-org:v3",
        "sdtc": "urn:hl7-org:sdtc"
    ]

    // MARK: - Public API

    /// Asynchronously parses an XML file from a given URL.
    /// - Parameters:
    ///   - url: The URL of the XML file to parse.
    ///   - completion: A closure that will be called with either the parsed records or a `ParserError`.
    public func parse(from url: URL, completion: @escaping (Result<ParsedRecords, ParserError>) -> Void) {
        let task = URLSession.shared.dataTask(with: url) { data, _, error in
            if let error = error {
                completion(.failure(ParserError.dataLoadingFailed(error)))
                return
            }
            
            guard let data = data else {
                completion(.failure(ParserError.dataLoadingFailed(URLError(.cannotDecodeContentData))))
                return
            }
            
            // Once data is loaded, attempt to parse it synchronously.
            do {
                let records = try self.parse(data: data)
                completion(.success(records))
            } catch let parserError as ParserError {
                completion(.failure(parserError))
            } catch {
                completion(.failure(.parsingFailed(error)))
            }
        }
        task.resume()
    }

    // MARK: - Parsing Logic

    /// The core parsing function that orchestrates the entire process.
    /// - Parameter data: The raw XML data to be parsed.
    /// - Returns: A `ParsedRecords` object containing all extracted medical data.
    /// - Throws: A `ParserError` if parsing fails at any stage.
    private func parse(data: Data) throws -> ParsedRecords {
        let parser = XMLParser(data: data)
        parser.delegate = self
        
        // The `XMLParserDelegate` methods will build the `root` element tree.
        // If parsing fails or the root is not set, throw an error.
        guard parser.parse(), let root = self.root else {
            throw ParserError.parsingFailed(parser.parserError ?? URLError(.cannotParseResponse))
        }

        // The first step after building the tree is to extract the patient's information.
        guard let patient = ingestPatient(from: root) else {
            throw ParserError.patientDataMissing
        }
        self.parsedRecords = ParsedRecords(patient: patient)
        
        // A dictionary mapping specific CDA template IDs to their corresponding ingestion functions.
        // This allows for modular and targeted data extraction from different sections of the document.
        let sectionIngestors: [String: (XMLElement) -> Void] = [
            "2.16.840.1.113883.10.20.22.2.6.1": ingestAllergies,
            "2.16.840.1.113883.10.20.22.2.5.1": ingestProblems,
            "2.16.840.1.113883.10.20.22.2.1.1": ingestMedications,
            "2.16.840.1.113883.10.20.22.2.2.1": ingestImmunizations,
            "2.16.840.1.113883.10.20.22.2.4.1": ingestVitals,
            "2.16.840.1.113883.10.20.22.2.3.1": ingestResults,
            "2.16.840.1.113883.10.20.22.2.7.1": ingestProcedures,
            "1.3.6.1.4.1.19376.1.5.3.1.3.4": ingestNotes
        ]

        // Find all <section> elements in the document.
        let allSections = root.findElements(path: ".//cda:section", namespaces: ns)
        
        // Iterate through each section to identify and process it.
        for section in allSections {
            // Find all <templateId> elements within the section.
            for templateIdElement in section.findElements(path: ".//cda:templateId", namespaces: ns) {
                // Get the 'root' attribute, which is the unique identifier for the section type.
                if let templateId = templateIdElement.attributes["root"] {
                    // If we have an ingestor function for this ID, call it.
                    if let ingestor = sectionIngestors[templateId] {
                        print("Ingesting section with template ID: \(templateId)")
                        ingestor(section)
                    }
                }
            }
        }
        
        // Return the fully populated records object.
        return self.parsedRecords!
    }
    
    // MARK: - Ingestion Methods
    
    /// Extracts patient demographic data from the XML tree.
    private func ingestPatient(from root: XMLElement) -> Patient? {
        guard let patientRole = root.findElement(path: ".//cda:recordTarget/cda:patientRole", namespaces: ns) else { return nil }
        guard let patientEl = patientRole.findElement(path: "cda:patient", namespaces: ns) else { return nil }

        let givenName = findText(in: patientEl, path: "cda:name/cda:given")
        let familyName = findText(in: patientEl, path: "cda:name/cda:family")
        let dob = findAttrib(in: patientEl, path: "cda:birthTime", attribute: "value")
        let mrn = findAttrib(in: patientRole, path: "cda:id", attribute: "extension")
        
        return Patient(
            mrn: mrn,
            givenName: givenName,
            familyName: familyName,
            dob: dob,
            gender: findAttrib(in: patientEl, path: "cda:administrativeGenderCode", attribute: "displayName"),
            maritalStatus: findAttrib(in: patientEl, path: "cda:maritalStatusCode", attribute: "displayName"),
            race: findAttrib(in: patientEl, path: "cda:raceCode", attribute: "displayName"),
            ethnicity: findAttrib(in: patientEl, path: "cda:ethnicGroupCode", attribute: "displayName"),
            deceased: findAttrib(in: patientEl, path: "sdtc:deceasedInd", attribute: "value") == "true",
            deceasedDate: findAttrib(in: patientEl, path: "sdtc:deceasedTime", attribute: "value")
        )
    }

    /// Extracts allergy data from the 'Allergies and Intolerances' section.
    private func ingestAllergies(in section: XMLElement) {
        for entry in section.findElements(path: ".//cda:entry", namespaces: ns) {
            // Skip entries that are explicitly marked as negative (e.g., "No known allergies").
            if let observation = entry.findElement(path: ".//cda:observation", namespaces: ns),
               observation.attributes["negationInd"] == "true" {
                continue
            }

            let allergy = Allergy(
                substance: findNameWithFallback(in: entry, path: ".//cda:participant/cda:participantRole/cda:playingEntity/cda:code"),
                reaction: findAttrib(in: entry, path: ".//cda:entryRelationship/cda:observation/cda:value", attribute: "displayName"),
                status: findAttrib(in: entry, path: ".//cda:act/cda:statusCode", attribute: "code"),
                effectiveDate: findAttrib(in: entry, path: ".//cda:effectiveTime/cda:low", attribute: "value")
            )
            parsedRecords?.allergies.append(allergy)
        }
    }

    /// Extracts health problem data from the 'Problem List' section.
    private func ingestProblems(in section: XMLElement) {
        for entry in section.findElements(path: ".//cda:entry", namespaces: ns) {
            guard let obs = entry.findElement(path: ".//cda:observation", namespaces: ns) else { continue }
            
            let problem = Problem(
                problemName: findNameWithFallback(in: obs, path: "cda:value"),
                status: findAttrib(in: obs, path: ".//cda:entryRelationship/cda:observation/cda:value", attribute: "displayName"),
                onsetDate: findAttrib(in: obs, path: "cda:effectiveTime/cda:low", attribute: "value"),
                resolvedDate: findAttrib(in: obs, path: "cda:effectiveTime/cda:high", attribute: "value")
            )
            parsedRecords?.problems.append(problem)
        }
    }

    /// Extracts medication data from the 'Medications' section.
    private func ingestMedications(in section: XMLElement) {
        for entry in section.findElements(path: ".//cda:entry/cda:substanceAdministration", namespaces: ns) {
            let medication = Medication(
                medicationName: findNameWithFallback(in: entry, path: ".//cda:consumable/cda:manufacturedProduct/cda:manufacturedMaterial/cda:code"),
                instructions: findNameWithFallback(in: entry, path: "cda:text"),
                status: findAttrib(in: entry, path: "cda:statusCode", attribute: "code"),
                startDate: findAttrib(in: entry, path: "cda:effectiveTime/cda:low", attribute: "value"),
                endDate: findAttrib(in: entry, path: "cda:effectiveTime/cda:high", attribute: "value")
            )
            parsedRecords?.medications.append(medication)
        }
    }
    
    /// Extracts immunization data from the 'Immunizations' section.
    private func ingestImmunizations(in section: XMLElement) {
        for entry in section.findElements(path: ".//cda:entry/cda:substanceAdministration", namespaces: ns) {
            let immunization = Immunization(
                vaccineName: findNameWithFallback(in: entry, path: "cda:consumable/cda:manufacturedProduct/cda:manufacturedMaterial/cda:code"),
                dateAdministered: findAttrib(in: entry, path: "cda:effectiveTime", attribute: "value")
            )
            parsedRecords?.immunizations.append(immunization)
        }
    }
    
    /// Extracts vital signs data from the 'Vital Signs' section.
    private func ingestVitals(in section: XMLElement) {
        for comp in section.findElements(path: ".//cda:component/cda:observation", namespaces: ns) {
            guard let vitalSign = findNameWithFallback(in: comp, path: "cda:code") else { continue }
            
            let vital = Vital(
                vitalSign: vitalSign,
                value: findAttrib(in: comp, path: "cda:value", attribute: "value"),
                unit: findAttrib(in: comp, path: "cda:value", attribute: "unit"),
                effectiveDate: findAttrib(in: comp, path: "cda:effectiveTime", attribute: "value")
            )
            parsedRecords?.vitals.append(vital)
        }
    }
    
    /// Extracts lab result data from the 'Results' section.
    private func ingestResults(in section: XMLElement) {
        for comp in section.findElements(path: ".//cda:component/cda:observation", namespaces: ns) {
            guard let testName = findNameWithFallback(in: comp, path: "cda:code") else { continue }

            var value: String?
            var unit: String?
            if let valueEl = comp.findElement(path: "cda:value", namespaces: ns) {
                // The value can be in an attribute or the element's text content.
                value = valueEl.attributes["value"] ?? valueEl.attributes["displayName"] ?? valueEl.text
                unit = valueEl.attributes["unit"]
            }

            let result = LabResult(
                testName: testName,
                value: value,
                unit: unit,
                referenceRange: findText(in: comp, path: ".//cda:referenceRange/cda:observationRange/cda:text"),
                interpretation: findAttrib(in: comp, path: "cda:interpretationCode", attribute: "displayName"),
                effectiveDate: findAttrib(in: comp, path: "cda:effectiveTime", attribute: "value")
            )
            parsedRecords?.results.append(result)
        }
    }
    
    /// Extracts procedure data from the 'Procedures' section.
    private func ingestProcedures(in section: XMLElement) {
        for proc in section.findElements(path: ".//cda:entry/cda:procedure", namespaces: ns) {
            // The procedure name can be in one of two common locations.
            let procName = findNameWithFallback(in: proc, path: "cda:code") ?? findNameWithFallback(in: proc, path: ".//cda:participant/cda:participantRole/cda:playingDevice/cda:code")

            let procedure = Procedure(
                procedureName: procName,
                date: findAttrib(in: proc, path: "cda:effectiveTime/cda:low", attribute: "value") ?? findAttrib(in: proc, path: "cda:effectiveTime", attribute: "value"),
                provider: findText(in: proc, path: ".//cda:performer/cda:assignedEntity/cda:assignedPerson/cda:name")
            )
            parsedRecords?.procedures.append(procedure)
        }
    }
    
    /// Extracts clinical notes from various sections that contain narrative text.
    private func ingestNotes(in section: XMLElement) {
        guard let textEl = section.findElement(path: "cda:text", namespaces: ns) else { return }
        // Get all text content from the element and its children, then trim whitespace.
        let noteContent = textEl.recursiveText().trimmingCharacters(in: .whitespacesAndNewlines)
        if noteContent.isEmpty { return }

        let noteTitle = section.findElement(path: "cda:title", namespaces: ns)?.text?.trimmingCharacters(in: .whitespacesAndNewlines) ?? "Clinical Note"
        let noteType = findAttrib(in: section, path: "cda:code", attribute: "displayName") ?? "Note"
        
        // The date and provider might be located at a higher level in the document structure.
        let noteDate = root?.findElement(path: ".//cda:encompassingEncounter/cda:effectiveTime/cda:low", namespaces: ns)?.attributes["value"]
                         ?? root?.findElement(path: "cda:effectiveTime", namespaces: ns)?.attributes["value"]
        
        let provider = root?.findElement(path: ".//cda:encompassingEncounter//cda:assignedPerson/cda:name", namespaces: ns)?.recursiveText().trimmingCharacters(in: .whitespacesAndNewlines)

        let note = Note(
            noteType: noteType,
            noteDate: noteDate,
            noteTitle: noteTitle,
            noteContent: noteContent,
            provider: provider
        )
        parsedRecords?.notes.append(note)
    }

    // MARK: - Helper Methods
    
    /// A simple helper to find the text content of a child element at a given path.
    private func findText(in element: XMLElement?, path: String) -> String? {
        return element?.findElement(path: path, namespaces: ns)?.text?.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// A simple helper to find the value of an attribute of a child element at a given path.
    private func findAttrib(in element: XMLElement?, path: String, attribute: String) -> String? {
        return element?.findElement(path: path, namespaces: ns)?.attributes[attribute]
    }
    
    /// A complex helper to find a human-readable name for a coded concept.
    /// It checks multiple common locations in a specific order of preference.
    private func findNameWithFallback(in element: XMLElement?, path: String) -> String? {
        guard let codeEl = element?.findElement(path: path, namespaces: ns) else { return nil }
        
        // 1. Prefer the 'displayName' attribute on the code element itself.
        if let displayName = codeEl.attributes["displayName"], !displayName.isEmpty {
            return displayName
        }
        
        // 2. If not found, look for an <originalText> element.
        if let originalTextEl = codeEl.findElement(path: "cda:originalText", namespaces: ns) {
            // 2a. Check for simple text inside <originalText>.
            if let text = originalTextEl.text, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                return text.trimmingCharacters(in: .whitespacesAndNewlines)
            }
            
            // 2b. If no simple text, check for a <reference> inside <originalText>.
            // This reference points to another element in the document by its ID.
            if let referenceEl = originalTextEl.findElement(path: "cda:reference", namespaces: ns),
               let refId = referenceEl.attributes["value"], refId.starts(with: "#") {
                
                let idToFind = String(refId.dropFirst())
                // Search the entire document from the root for the referenced element.
                if let referencedEl = self.root?.findElement(byID: idToFind) {
                    return referencedEl.recursiveText().trimmingCharacters(in: .whitespacesAndNewlines)
                }
            }
        }
        
        // 3. As a final fallback, use the text content of the <code> element itself.
        if let text = codeEl.text, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return text.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        
        return nil
    }


    // MARK: - XMLParserDelegate Methods

    /// Called when the parser starts processing the document. Resets all state.
    func parserDidStartDocument(_ parser: XMLParser) {
        root = nil
        currentElement = nil
        namespaceMapping = [:]
    }

    /// Called for each opening tag (`<element>`). This is where the custom element tree is built.
    func parser(_ parser: XMLParser, didStartElement elementName: String, namespaceURI: String?, qualifiedName qName: String?, attributes attributeDict: [String : String] = [:]) {
        // 1. Learn namespace prefixes (e.g., "xmlns:cda") as they are encountered.
        for (key, value) in attributeDict where key.starts(with: "xmlns:") {
            let prefix = String(key.dropFirst(6)) // e.g., "cda"
            namespaceMapping[value] = prefix // Map the URI (value) to the prefix.
        }
        
        // 2. Manually construct the element name with its learned prefix (e.g., "cda:patient").
        var finalElementName = elementName
        if let uri = namespaceURI, let prefix = namespaceMapping[uri] {
            finalElementName = "\(prefix):\(elementName)"
        }
        
        // 3. Create the new XMLElement and link it into the tree structure.
        let newElement = XMLElement(name: finalElementName, attributes: attributeDict)
        newElement.parent = currentElement
        currentElement?.children.append(newElement)
        
        // If this is the first element, it becomes the root.
        if root == nil {
            root = newElement
        }
        // Move the 'currentElement' pointer down to the new element.
        currentElement = newElement
    }

    /// Called when character data is found inside an element. Appends it to the current element's text.
    func parser(_ parser: XMLParser, foundCharacters string: String) {
        currentElement?.text = (currentElement?.text ?? "") + string
    }

    /// Called for each closing tag (`</element>`). Moves the 'currentElement' pointer back up the tree.
    func parser(_ parser: XMLParser, didEndElement elementName: String, namespaceURI: String?, qualifiedName qName: String?) {
        currentElement = currentElement?.parent
    }

    /// Called if a parsing error occurs. The error is ultimately handled by the `parse(data:)` function's catch block.
    func parser(_ parser: XMLParser, parseErrorOccurred parseError: Error) {
        // Errors are handled by the throwing parse() function's guard statement.
    }
}

/// A helper class representing a single element in our custom XML tree.
/// This makes the parsed XML much easier to navigate and query than using the raw `XMLParser` delegates directly.
class XMLElement {
    let name: String
    let attributes: [String: String]
    var children: [XMLElement] = []
    var text: String?
    weak var parent: XMLElement? // A weak reference to avoid retain cycles.

    init(name: String, attributes: [String: String]) {
        self.name = name
        self.attributes = attributes
    }
    
    /// Gathers all text from this element and all its children, recursively.
    func recursiveText() -> String {
        return (text ?? "").trimmingCharacters(in: .whitespacesAndNewlines) + children.map { $0.recursiveText() }.joined(separator: " ")
    }

    /// Finds a descendant element anywhere in the subtree by its "ID" attribute.
    func findElement(byID id: String) -> XMLElement? {
        if self.attributes["ID"] == id {
            return self
        }
        for child in children {
            if let found = child.findElement(byID: id) {
                return found
            }
        }
        return nil
    }
    
    /// A convenience method to find the first element matching a given path.
    func findElement(path: String, namespaces: [String: String]) -> XMLElement? {
        return findElements(path: path, namespaces: namespaces).first
    }
    
    /// Finds a list of elements matching a simple XPath-like query.
    /// Supports direct children (`a/b`) and recursive descendants (`.//b`).
    func findElements(path: String, namespaces: [String: String]) -> [XMLElement] {
        // To simplify matching, this implementation removes namespace prefixes from the path
        // because the XMLElement names have already been constructed with these prefixes.
        var sanitizedPath = path
        for prefix in namespaces.keys {
            sanitizedPath = sanitizedPath.replacingOccurrences(of: "\(prefix):", with: "")
        }

        let isRecursive = sanitizedPath.starts(with: ".//")
        // Remove the path operators to get the component names.
        let finalPath = isRecursive ? String(sanitizedPath.dropFirst(3)) : sanitizedPath
        let components = finalPath.split(separator: "/").map(String.init)
        
        guard let firstComponent = components.first else { return [] }
        
        var currentElements: [XMLElement]
        
        // Start the search. If recursive, search all descendants; otherwise, search direct children.
        if isRecursive {
            currentElements = self.findDescendants(named: firstComponent)
        } else {
            currentElements = self.children.filter { $0.name == firstComponent }
        }
        
        // For the remaining path components, filter the results from the previous step.
        let remainingComponents = components.dropFirst()
        for component in remainingComponents {
            var nextElements: [XMLElement] = []
            for element in currentElements {
                nextElements.append(contentsOf: element.children.filter { $0.name == component })
            }
            currentElements = nextElements
        }
        
        return currentElements
    }
    
    /// A helper function to find all descendant elements with a given name, recursively.
    private func findDescendants(named name: String) -> [XMLElement] {
        var found: [XMLElement] = []
        for child in self.children {
            if child.name == name {
                found.append(child)
            }
            // Continue the search down the tree.
            found.append(contentsOf: child.findDescendants(named: name))
        }
        return found
    }
}
