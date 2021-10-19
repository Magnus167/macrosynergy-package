import numpy as np

class ConvergeRow(object):
    """
    Class designed to receive a row of weights, where at least one weight in the
    aforementioned row exceeds the permitted upper-bound, and subsequently redistributes
    the excess evenly across all cross-sections. The reason for the even distribution is
    to retain the weighting proportions received: the weights are not arbitrary but
    instead determined according to a specific method. Therefore, the Class will simply
    aim to dilute the influence any cross-section above the maximum amount but retain
    the ratio between the remaining weights.
    """

    def __init__(self, row, m_weight, active_cross, r_length):
        """
        Class's Constructor.

        :param <np.ndarray> row: Array of weights.
        :param <Float> m_weight: Maximum weight.
        :param <int> active_cross: Number of active cross-sections held on the row.
        :param <int> r_length: Length of the respective row.

        """
        self.row = row
        self.r_length = r_length
        self.maximum = self.max_row()
        self.m_weight = m_weight
        self.active_cross = active_cross
        
        self.m_index = self.max_index()
        self.margin = 0.001 
        
    def distribute(self):
        """
        Initiates an indefinite While Loop until the weights converge below the
        (max_weight + margin). Will evenly redistribute the excess weight across all
        active cross-sections, and will compute the maximum weight, the number of cross-
        sections above the threshold and the excess weight dynamically: through each
        iteration.

        """

        while True:

            excess = self.max_row() - self.m_weight

            excess_cross = self.excess_count()
            indexing = self.index_row()
            
            if excess_cross.size == 1:
                self.row[self.m_index] -= excess
                
            elif excess_cross.size > 1:
                for index in excess_cross:
                    indexing[index] = self.m_weight
                    
                self.row = np.array(list(indexing.values()))
                excess = 1.0 - np.nansum(self.row)
            else:
                break

            amount = excess / self.active_cross
            self.row += amount
            

    def max_row(self):
        """
        Determines the maximum weight in the row. Will return the weight value.

        """
        return np.nanmax(self.row)

    def excess_count(self):
        """
        Calculates the number of weights that exceed the threshold. This can change
        through each iteration, so the calculation occurs dynamically.

        Will return an Array of the indices that satifsy the condition.
        """

        row_copy = self.row.copy()

        return np.where((row_copy - self.m_weight) > 0.001)[0]

    def max_index(self):
        """
        Will return the index of the maximum value. Integer.

        """
        return np.where(self.row == self.maximum)[0][0]

    def index_row(self):
        """
        Function used to design a dictionary where the keys are indices of the row, and
        the values are the weights of the row. Dictionaries are supported by a data
        structure called a Hashmap and are subsequently computationally very efficient
        assuming an effective Hash Function has been designed. Potentially O(1) look-up
        time if collisions are avoided.

        Returns a dictionary.
        """
        return dict(zip(range(self.r_length), self.row))
