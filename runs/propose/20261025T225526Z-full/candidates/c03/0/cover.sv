// P3: receiver output held under back-pressure, then accepted.
module cov_P3 (
  input logic       clk,
  input logic       rst,
  input logic [7:0] m_axis_tdata,
  input logic       m_axis_tvalid,
  input logic       m_axis_tready,
  input logic       overrun_error
);

  logic [3:0] stall_cnt;
  logic [7:0] data_hold;

  always @(posedge clk) begin
    if (rst) begin
      stall_cnt <= 4'd0;
      data_hold <= 8'h00;
    end else begin
      data_hold <= m_axis_tdata;
      if (overrun_error) begin
        stall_cnt <= 4'd0;
      end else if (m_axis_tvalid && !m_axis_tready) begin
        if (stall_cnt != 4'd0 && m_axis_tdata != data_hold) begin
          stall_cnt <= 4'd1;
        end else if (stall_cnt != 4'd15) begin
          stall_cnt <= stall_cnt + 4'd1;
        end
      end else begin
        stall_cnt <= 4'd0;
      end
    end
  end

  P3_rx_backpressure_hold: cover property (@(posedge clk) disable iff (rst)
    m_axis_tvalid && m_axis_tready && !overrun_error &&
    stall_cnt >= 4'd4 && m_axis_tdata == data_hold && m_axis_tdata == 8'hA5);

endmodule

bind uart_rx cov_P3 u_cov_P3 (.*);
